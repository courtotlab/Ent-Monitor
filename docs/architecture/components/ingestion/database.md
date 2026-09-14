# Ingestion Layer Database Operations & Data Formats

- **Location:** [layers/ingestion/shared/queries.py](../../../../layers/ingestion/shared/queries.py) & [layers/ingestion/shared/models.py](../../../../layers/ingestion/shared/models.py)  
- **Purpose:** Documents all database reads, writes, and normalized schemas used during data ingestion.
- **Authoritative Schema:** For full table DDL, column types, constraints, and pgvector indexes, see [Database Schema Reference](../../../database/schema.md).

---

## 1. Normalized Post Schema (`NormalizedPost`)

All scrapers (TikTok, Instagram, YouTube, Reddit) normalize raw, platform-specific JSON responses into a unified Python dataclass defined in `layers/ingestion/shared/models.py`.

```python
@dataclass
class NormalizedPost:
    post_id: str                          # Unique platform ID (e.g. video ID, submission ID)
    platform: str                         # "tiktok" | "instagram" | "youtube" | "reddit"
    source: str                           # Ingestion track (see table below)
    creator_id: str                       # Monitored creator handle or username
    caption_text: str                     # Title or caption text
    transcript_text: str | None = None    # Video subtitles or Reddit selftext
    url: str | None = None                # Direct URL to the post
    posted_at: str | None = None          # ISO 8601 timestamp string from platform
    collected_at: str | None = None       # ISO 8601 timestamp when scraped
    engagement: dict[str, object] = field(default_factory=dict)
```

### Engagement Sub-Schema (`engagement`)
```json
{
  "likes": 1420,
  "comments": 85,
  "shares": 310,
  "views": 45000
}
```

### Valid Post `source` Values
| Source String | Producing Subsystem | Meaning |
|---|---|---|
| `creator_monitor` | Social Media | Post scraped directly from a monitored creator in `creators` table |
| `engager` | Social Media | Post scraped from a commenter found on a creator's post |
| `explore_feed` | Social Media | Post scraped from platform trending / FYP feed |
| `reddit` | Social Media | Submission collected from targeted health/parenting subreddits |
| `gtrends_search` | Google Trends | Inline reactive video search triggered by a search spike |
| `gdelt_news` | GDELT | Inline reactive video search triggered by clinical news break |

---

## 2. Target Database Tables Summary

| Table | Operation | Triggered By | What is Written / Read |
|---|---|---|---|
| `posts` | `INSERT / UPSERT` | All social scrapers, GTrends inline, GDELT inline | Raw social video/post items |
| `trends` | `INSERT` (stub) | Google Trends worker | Initial stub trend row for detected spikes |
| `trend_signals` | `INSERT` | Google Trends & GDELT | External trend signals (`gt_spike`, `news_match`) |
| `gdelt_seen_articles` | `SELECT` / `UPSERT` | GDELT worker | URL deduplication cache for news stories |
| `pipeline_state` | `SELECT` / `UPDATE` | GDELT worker | Checkpoint tracking last successfully polled GKG batch |
| `creators` | `SELECT` | Social Media orchestrator | Watchlist of monitored creator handles |
| `sbert_anchors` | `SELECT` | GTrends & GDELT workers | Active clinical anchor embeddings for semantic gating |

---

## 3. Database Write Operations

### 3.1 `insert_post()` Ingest Social Post
- **Target Table:** `posts`
- **Function:** `insert_post(post: RawPostDict, sbert_score: float | None = None, matched_anchor_id: int | None = None) -> bool`
- **Called by:** `tiktok.py`, `instagram.py`, `youtube.py`, `reddit.py`, `gtrends.py`, `gdelt.py`

#### SQL Query:
```sql
INSERT INTO posts (
    post_id, platform, source,
    creator_id, caption_text, transcript_text, url,
    likes, comments, shares, views,
    collected_at, posted_at, sbert_score, matched_anchor_id
) VALUES (
    %s, %s, %s,
    (SELECT creator_id FROM creators WHERE creator_id = %s AND platform = %s),
    %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s, %s
)
ON CONFLICT (post_id, platform) DO UPDATE SET
    source = COALESCE(EXCLUDED.source, posts.source),
    creator_id = COALESCE(EXCLUDED.creator_id, posts.creator_id),
    caption_text = COALESCE(EXCLUDED.caption_text, posts.caption_text),
    transcript_text = COALESCE(EXCLUDED.transcript_text, posts.transcript_text),
    url = COALESCE(EXCLUDED.url, posts.url),
    likes = GREATEST(COALESCE(EXCLUDED.likes, 0), COALESCE(posts.likes, 0)),
    comments = GREATEST(COALESCE(EXCLUDED.comments, 0), COALESCE(posts.comments, 0)),
    shares = GREATEST(COALESCE(EXCLUDED.shares, 0), COALESCE(posts.shares, 0)),
    views = GREATEST(COALESCE(EXCLUDED.views, 0), COALESCE(posts.views, 0)),
    collected_at = EXCLUDED.collected_at,
    posted_at = COALESCE(EXCLUDED.posted_at, posts.posted_at),
    matched_anchor_id = CASE
        WHEN EXCLUDED.sbert_score IS NOT NULL AND (posts.sbert_score IS NULL OR EXCLUDED.sbert_score > posts.sbert_score) 
        THEN EXCLUDED.matched_anchor_id
        ELSE posts.matched_anchor_id
    END,
    sbert_score = CASE
        WHEN EXCLUDED.sbert_score IS NOT NULL AND (posts.sbert_score IS NULL OR EXCLUDED.sbert_score > posts.sbert_score) 
        THEN EXCLUDED.sbert_score
        ELSE posts.sbert_score
    END
RETURNING (xmax = 0) AS is_insert;
```

#### Input / Output:
- **Input:** `post` dictionary (`RawPostDict`), optional `sbert_score: float`, optional `matched_anchor_id: int`.
- **Output:** `bool` returns `True` if a brand new row was inserted (`xmax = 0`), or `False` if an existing row was updated.
- **Key Behavior:**
  - Standard social scrapers pass `sbert_score = None`, leaving it as `NULL` for the downstream Preprocessing layer.
  - Inline cross-fetches (from GTrends/GDELT) compute SBERT scores on the fly and pass them in directly.
  - On conflict, engagement metrics (`likes`, `comments`, etc.) are monotonically updated using `GREATEST()`.

---

### 3.2 `insert_gt_spike()` Record Google Trends Spike
- **Target Tables:** `trends` & `trend_signals`
- **Function:** `insert_gt_spike(signal_data: Json, linked_trend_id: str) -> None`
- **Called by:** `layers/ingestion/search/gtrends.py`

#### SQL Queries:
```sql
  /* 1. Create trend stub if not existing */
INSERT INTO trends (trend_id, trend_name, label, risk_score, discovery_source)
VALUES (%s, %s, 'MODERATE', 0.5, 'gtrends_search')
ON CONFLICT DO NOTHING;

  /* 2. Log detected signal */
INSERT INTO trend_signals (
    signal_type, signal_data,
    search_platforms, search_status, linked_trend_id
) VALUES (
    'gt_spike', %s,
    '["tiktok","instagram"]'::jsonb, 'pending', %s
);
```

#### Input / Output:
- **Input:**
  - `signal_data: Json` Payload containing search term, traffic volume, and filtered rising queries:
    ```json
    {
      "gt_term": "ear candling",
      "gt_traffic": "50K+ searches",
      "gt_rising_queries": [
        { "query": "ear candling at home", "score": 0.58 }
      ]
    }
    ```
  - `linked_trend_id: str` Deterministic hash or slug ID (e.g. `make_trend_id(title)`).
- **Output:** `None`

### 3.3 `insert_news_trend_signal()` Record GDELT News Signal
- **Target Table:** `trend_signals`
- **Function:** `insert_news_trend_signal(signal_data: Json) -> None`
- **Called by:** `layers/ingestion/news/gdelt.py`

#### SQL Query:
```sql
INSERT INTO trend_signals (
    signal_type, signal_data,
    search_platforms,
    search_status, detected_at
) VALUES (
    'news_match', %s,
    '["tiktok","instagram"]', 'pending', NOW()
)
ON CONFLICT DO NOTHING;
```

#### Input / Output:
- **Input:** `signal_data: Json`
  ```json
  {
    "news_source_url": "https://example.com/hospital-ear-injury",
    "news_source_name": "BBC News",
    "news_article_title": "Doctors warn against viral TikTok ear cleaning hack",
    "news_article_date": "2026-09-13T06:00:00Z",
    "news_sbert_score": 0.52,
    "news_behavioral_extract": "A 10-year-old child was treated for severe burns...",
    "news_matched_term": "ear cleaning hack"
  }
  ```
- **Output:** `None`

### 3.4 `upsert_gdelt_seen_url()` Mark News Article Seen
- **Target Table:** `gdelt_seen_articles`
- **Function:** `upsert_gdelt_seen_url(url: str) -> None`

#### SQL Query:
```sql
INSERT INTO gdelt_seen_articles (url, seen_at)
VALUES (%s, NOW())
ON CONFLICT (url) DO UPDATE SET seen_at = NOW();
```

### 3.5 `update_gdelt_last_polled_url()` Save Polling Checkpoint
- **Target Table:** `pipeline_state`
- **Function:** `update_gdelt_last_polled_url(url: str) -> None`

#### SQL Query:
```sql
UPDATE pipeline_state 
SET state_value = jsonb_build_object('last_url', %s, 'last_polled_at', NOW()), 
    updated_at = NOW() 
WHERE state_key = 'gdelt_poll';
```

---

## 4. Database Read Operations

| Function | Source Table | Query / Filter | Output Type | Used By |
|---|---|---|---|---|
| `get_all_creators()` | `creators` | `SELECT creator_id, platform FROM creators` | `list[tuple[str, str]]` | Social Media Orchestrator |
| `fetch_sbert_anchors_with_source()` | `sbert_anchors` | `SELECT anchor_id, embedding, source FROM sbert_anchors WHERE active = TRUE` | `list[tuple[int, str, list[float]]]` | GTrends & GDELT SBERT gates |
| `get_recent_gt_spikes()` | `trend_signals` | `WHERE signal_type = 'gt_spike' AND detected_at >= NOW() - INTERVAL '7 days'` | `set[str]` | Google Trends (Deduplication) |
| `get_recent_gdelt_seen_urls()` | `gdelt_seen_articles` | `WHERE seen_at >= NOW() - INTERVAL '48 hours'` | `set[str]` | GDELT Funnel Stage 3 |
| `get_gdelt_last_polled_url()` | `pipeline_state` | `WHERE state_key = 'gdelt_poll'` | `str \| None` | GDELT Poller Checkpoint |
