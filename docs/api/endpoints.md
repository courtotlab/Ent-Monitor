# API Endpoints

The Next.js dashboard (App Engine) fetches data from PostgreSQL via these API routes.
All routes use `force-dynamic` to bypass Next.js caching and always query the live database.

---

## GET `/api/dashboard/stats`

Returns aggregate statistics for the dashboard overview cards.

**SQL:**
```sql
SELECT
  (SELECT COUNT(*) FROM trends WHERE label = 'HIGH') AS harmful_count,
  (SELECT COUNT(*) FROM trends WHERE label = 'MODERATE') AS concerning_count,
  (SELECT COUNT(*) FROM trends) AS total_trends_classified,
  (SELECT COUNT(*) FROM creators) AS active_creators
```

**Response Schema:**
```json
{
  "harmful_count": "string (numeric)",
  "concerning_count": "string (numeric)",
  "total_trends_classified": "string (numeric)",
  "active_creators": "string (numeric)"
}
```

**Example:**
```json
{
  "harmful_count": "12",
  "concerning_count": "45",
  "total_trends_classified": "108",
  "active_creators": "24"
}
```

> **Note:** PostgreSQL `COUNT(*)` returns `bigint`, which the `pg` driver serializes as a string. The frontend parses these with `parseInt()`.

---

## GET `/api/dashboard/chart`

Returns a 90-day time-series of trend activity grouped by risk label, for the main dashboard chart.

**SQL:**
```sql
SELECT
  TO_CHAR(DATE(COALESCE(t.last_seen_at, t.first_detected_at) AT TIME ZONE 'UTC'), 'YYYY-MM-DD') AS date,
  COUNT(*) FILTER (WHERE t.label = 'HIGH') AS harmful,
  COUNT(*) FILTER (WHERE t.label = 'MODERATE') AS concerning,
  COUNT(*) FILTER (WHERE t.label = 'LOW') AS safe
FROM trends t
WHERE COALESCE(t.last_seen_at, t.first_detected_at) >= NOW() - INTERVAL '90 days'
GROUP BY DATE(COALESCE(t.last_seen_at, t.first_detected_at) AT TIME ZONE 'UTC')
ORDER BY date
```

**Response Schema:**
```json
{
  "chart_data": [
    {
      "date": "YYYY-MM-DD",
      "harmful": "string (numeric)",
      "concerning": "string (numeric)",
      "safe": "string (numeric)"
    }
  ]
}
```

**Example:**
```json
{
  "chart_data": [
    { "date": "2026-08-01", "harmful": "2", "concerning": "5", "safe": "12" },
    { "date": "2026-08-02", "harmful": "3", "concerning": "4", "safe": "10" }
  ]
}
```

---

## GET `/api/dashboard/recent-trends`

Returns the 10 most recently active trends for the dashboard sidebar.

**SQL:**
```sql
SELECT
  trend_id, label, risk_score, post_count,
  COALESCE(platforms, '[]'::jsonb) AS platforms,
  lifecycle_status, first_detected_at, last_seen_at,
  trend_name, abstract, verification_status, discovery_source,
  velocity_growth_rate,
  COALESCE(slang_terms, '[]'::jsonb) AS slang_terms
FROM trends
ORDER BY GREATEST(first_detected_at, COALESCE(last_seen_at, first_detected_at)) DESC
LIMIT 10
```

**Response Schema:**
```json
{
  "trends": [
    {
      "trend_id": "string",
      "label": "HIGH | MODERATE | LOW",
      "risk_score": "number (0.0-1.0)",
      "post_count": "number",
      "platforms": ["string"],
      "lifecycle_status": "string",
      "first_detected_at": "ISO 8601 timestamp",
      "last_seen_at": "ISO 8601 timestamp | null",
      "trend_name": "string",
      "abstract": "string | null",
      "verification_status": "CONFIRMED | PROVISIONAL | INSUFFICIENT_EVIDENCE",
      "discovery_source": "string | null",
      "velocity_growth_rate": "number | null",
      "slang_terms": ["string"]
    }
  ]
}
```

---

## GET `/api/trends`

Returns all trends, sorted by most recent activity.

**SQL:**
```sql
SELECT
  trend_id, label, risk_score, post_count,
  COALESCE(platforms, '[]'::jsonb) AS platforms,
  lifecycle_status, first_detected_at, last_seen_at,
  trend_name, abstract, verification_status,
  discovery_source, velocity_growth_rate,
  COALESCE(slang_terms, '[]'::jsonb) AS slang_terms
FROM trends
ORDER BY last_seen_at DESC NULLS LAST, first_detected_at DESC
```

**Response Schema:** Same as `/api/dashboard/recent-trends` but without `LIMIT 10`.

```json
{
  "trends": [
    {
      "trend_id": "string",
      "label": "HIGH | MODERATE | LOW",
      "risk_score": "number",
      "post_count": "number",
      "platforms": ["string"],
      "lifecycle_status": "string",
      "first_detected_at": "ISO 8601",
      "last_seen_at": "ISO 8601 | null",
      "trend_name": "string",
      "abstract": "string | null",
      "verification_status": "string",
      "discovery_source": "string | null",
      "velocity_growth_rate": "number | null",
      "slang_terms": ["string"]
    }
  ]
}
```

---

## GET `/api/trends/[id]/details`

Returns full clinical detail for a single trend, including linked posts and daily volume chart data.

**SQL (3 queries):**

**1. Trend:**
```sql
SELECT
  trend_id, label, risk_score, post_count,
  COALESCE(platforms, '[]'::jsonb) AS platforms,
  lifecycle_status, first_detected_at, last_seen_at,
  trend_name, abstract, verification_status,
  discovery_source, velocity_growth_rate, should_monitor,
  COALESCE(evidence, '[]'::jsonb) AS evidence,
  harm_mechanism,
  COALESCE(lifecycle_history, '[]'::jsonb) AS lifecycle_history,
  COALESCE(slang_terms, '[]'::jsonb) AS slang_terms
FROM trends WHERE trend_id = $1
```

**2. Linked posts:**
```sql
SELECT
  post_id, platform, creator_id, caption_text, url,
  likes, comments, shares, views,
  collected_at, posted_at, sbert_score
FROM posts WHERE linked_trend_id = $1
ORDER BY collected_at DESC
```

**3. Daily volume:**
```sql
SELECT
  TO_CHAR(DATE(COALESCE(posted_at, collected_at) AT TIME ZONE 'UTC'), 'YYYY-MM-DD') AS date,
  COUNT(*) AS count
FROM posts WHERE linked_trend_id = $1
GROUP BY DATE(COALESCE(posted_at, collected_at) AT TIME ZONE 'UTC')
ORDER BY date ASC
```

**Response Schema:**
```json
{
  "trend": {
    "trend_id": "string",
    "label": "HIGH | MODERATE | LOW",
    "risk_score": "number",
    "post_count": "number",
    "platforms": ["string"],
    "lifecycle_status": "string",
    "first_detected_at": "ISO 8601",
    "last_seen_at": "ISO 8601 | null",
    "trend_name": "string",
    "abstract": "string | null",
    "verification_status": "string",
    "discovery_source": "string | null",
    "velocity_growth_rate": "number | null",
    "should_monitor": "boolean",
    "evidence": [
      {
        "url": "string",
        "title": "string",
        "pmid": "string | null",
        "snippet": "string"
      }
    ],
    "harm_mechanism": "string | null",
    "lifecycle_history": [
      {
        "date": "ISO 8601",
        "status": "string",
        "post_count": "number"
      }
    ],
    "slang_terms": ["string"]
  },
  "posts": [
    {
      "post_id": "string",
      "platform": "string",
      "creator_id": "string | null",
      "caption_text": "string",
      "url": "string | null",
      "likes": "number | null",
      "comments": "number | null",
      "shares": "number | null",
      "views": "number | null",
      "collected_at": "ISO 8601",
      "posted_at": "ISO 8601 | null",
      "sbert_score": "number"
    }
  ],
  "chart_data": [
    {
      "date": "YYYY-MM-DD",
      "count": "string (numeric)"
    }
  ]
}
```

---

## Error Response (All Endpoints)

On failure, all endpoints return:

```json
{
  "error": "string"
}
```

With HTTP status `500`.

The `/api/trends/[id]/details` endpoint also returns `404` if the trend ID is not found.
