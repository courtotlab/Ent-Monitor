# Analysis Layer Database Operations

- **Location:** [layers/analysis/db/queries.py](../../../../layers/analysis/db/queries.py)
- **Component Overview:** [Analysis Component Overview](overview.md)
- **Authoritative Schema:** For complete table schemas, constraints, and pgvector types for `posts`, `trends`, `agent_runs`, and `trend_signals`, see [Database Schema Reference](../../../database/schema.md).

---

## 1. Read Operations

### [fetch_unprocessed_posts(threshold=0.40)](../../../../layers/analysis/db/queries.py#L15)

Fetches all posts that passed SBERT preprocessing but have not yet been classified by the analysis agent.

```sql
SELECT post_id, platform, caption_text, sbert_score, creator_id,
       likes, views, posted_at, matched_anchor_id
FROM posts
WHERE sbert_score >= 0.40
  AND gate4_category IS NULL
```

Called by: `orchestrator.py` before invoking `run_analysis()`.

### [find_nearest_trend(centroid, threshold=0.95)](../../../../layers/analysis/db/queries.py#L62)

Uses pgvector's HNSW approximate nearest-neighbor index to find the closest existing trend to a cluster's centroid. Used by OBSERVE to match new clusters to known trends.

```sql
SELECT trend_id, label, risk_score, search_context, post_count,
       lifecycle_status, verification_status, last_seen_at,
       last_verified_at,
       1 - (centroid <=> $1::vector) AS similarity
FROM trends
WHERE centroid IS NOT NULL
  AND (centroid <=> $1::vector) < $2
ORDER BY centroid <=> $1::vector
LIMIT 1
```

Distance threshold is computed as `1.0 - cosine_threshold`. Default cosine threshold: `0.95`. Overridable via `OBSERVE_MATCH_THRESHOLD` env var.

### [get_recent_post_count(trend_id, days=7)](../../../../layers/analysis/db/queries.py#L43)

Counts posts linked to a trend within the last N days. Used by DECIDE to compute the smart `should_monitor` scheduling rule.

```sql
SELECT COUNT(*)
FROM posts
WHERE linked_trend_id = $1
  AND COALESCE(posted_at, collected_at) >= NOW() - ($2 * INTERVAL '1 day')
```

### [fetch_pending_early_warnings()](../../../../layers/analysis/db/queries.py#L560)

Fetches all pending early-warning signals stored by OBSERVE across previous runs. Used to check whether enough similar lone posts have accumulated for promotion.

```sql
SELECT signal_id, signal_data, detected_at
FROM trend_signals
WHERE signal_type = 'early_warning'
  AND dismissed = FALSE
  AND search_status = 'pending'
ORDER BY detected_at
```

### [fetch_trends_to_monitor()](../../../../layers/analysis/db/queries.py#L609)

Fetches all trends flagged for active velocity monitoring. Used by the Monitoring layer (not the analysis layer directly), but defined in `db/queries.py`.

```sql
SELECT trend_id, trend_name, label, slang_terms,
       centroid::text, post_count,
       first_detected_at, velocity_growth_rate, velocity_check_count
FROM trends
WHERE should_monitor = TRUE
  AND slang_terms IS NOT NULL
  AND jsonb_array_length(slang_terms) > 0
  AND centroid IS NOT NULL
  AND label IN ('HIGH', 'MODERATE')
  AND (last_seen_at IS NULL OR last_seen_at >= NOW() - INTERVAL '14 days')
```

---

## 2. Write Operations

### [create_agent_run(run_id, posts_input)](../../../../layers/analysis/db/queries.py#L197)

Inserts a new tracking row at the start of each run. Called by `run_analysis()` before graph invocation.

```sql
INSERT INTO agent_runs (run_id, started_at, status, posts_input)
VALUES ($1, NOW(), 'running', $2)
ON CONFLICT (run_id) DO NOTHING
```

### [complete_agent_run(...)](../../../../layers/analysis/db/queries.py#L214)

Updates the tracking row at the end of each run with duration, cluster counts, and an optional Markdown report summary.

```sql
UPDATE agent_runs
SET completed_at      = NOW(),
    duration_seconds  = EXTRACT(EPOCH FROM (NOW() - started_at)),
    status            = $1,
    clusters_formed   = $2,
    trends_classified = $3,
    report_markdown   = $4,
    error_message     = $5
WHERE run_id = $6
```

### [write_cluster_to_db(state, centroid)](../../../../layers/analysis/db/queries.py#L255)

The main classification write. Upserts the trend row and reassigns all cluster posts. Called by REPORT (HIGH/MODERATE) and DECIDE (LOW trends that are not isolated/out_of_scope).

#### Trend UPSERT

```sql
INSERT INTO trends
  (trend_id, label, risk_score, post_count, platforms, slang_terms,
   verification_status, lifecycle_status, first_detected_at, last_seen_at,
   last_verified_at, abstract, search_context, trend_name, harm_mechanism,
   evidence, centroid, lifecycle_history, should_monitor, velocity_check_count)
VALUES (...)
ON CONFLICT (trend_id) DO UPDATE SET
    post_count          = trends.post_count + EXCLUDED.post_count,
    risk_score          = GREATEST(trends.risk_score, EXCLUDED.risk_score),
    label               = CASE
                            WHEN EXCLUDED.label = 'HIGH' THEN 'HIGH'
                            WHEN EXCLUDED.label = 'MODERATE' AND trends.label != 'HIGH' THEN 'MODERATE'
                            ELSE trends.label
                          END,
    verification_status = EXCLUDED.verification_status,
    lifecycle_status    = EXCLUDED.lifecycle_status,
    last_verified_at    = EXCLUDED.last_verified_at,
    lifecycle_history   = COALESCE(trends.lifecycle_history, '[]'::jsonb) ||
                          jsonb_build_array(...),
    platforms           = (SELECT COALESCE(jsonb_agg(DISTINCT elem), '[]'::jsonb) FROM (...) combined),
    slang_terms         = (SELECT COALESCE(jsonb_agg(DISTINCT elem), '[]'::jsonb) FROM (...) combined),
    last_seen_at        = EXCLUDED.last_seen_at,
    centroid            = COALESCE(EXCLUDED.centroid, trends.centroid),
    should_monitor      = EXCLUDED.should_monitor OR trends.should_monitor
```

Label escalation rule: `HIGH` always wins; `MODERATE` only overwrites non-`HIGH`; `LOW` never overwrites.

Note: `last_verified_at` is refreshed on every full-pipeline write. Fast-path merges (`merge_posts_into_trend`) intentionally do NOT refresh it.

#### Post Reassignment ([_reassign_and_update_posts](../../../../layers/analysis/db/queries.py#L142))

For each post in the cluster:

```sql
/* If previously linked to a different trend, decrement that trend's count */
UPDATE trends SET post_count = GREATEST(post_count - 1, 0) WHERE trend_id = $old_trend_id

/* Link this post to the new trend */
UPDATE posts
SET gate4_category  = $label,
    linked_trend_id = $trend_id
WHERE post_id = $post_id AND platform = $platform
```

#### Post Count Self-Heal ([_recompute_post_count](../../../../layers/analysis/db/queries.py#L174))

After every write, the post count is recomputed from the actual FK relationships to prevent drift from partial updates:

```sql
SELECT COUNT(*) FROM posts WHERE linked_trend_id = $trend_id
UPDATE trends SET post_count = $actual WHERE trend_id = $trend_id
```

#### Centroid Merge ([_merge_centroids](../../../../layers/analysis/db/queries.py#L113))

When updating an existing trend, the old and new centroids are merged as a weighted average then L2-normalized:

```
merged = (old_centroid * old_count + new_centroid * new_count) / total_count
merged = merged / ||merged||
```

### [merge_posts_into_trend(trend_id, posts, new_centroid)](../../../../layers/analysis/db/queries.py#L389)

Fast-path merge for known trends (called by the [merge_known](nodes/merge.md) helper). Updates without a full UPSERT and intentionally skips refreshing `last_verified_at`.

```sql
/* Fetch current state */
SELECT label, risk_score, post_count, platforms, centroid::text,
       last_seen_at, lifecycle_status, verification_status
FROM trends WHERE trend_id = $1

/* Update trend (resurfacing detection, centroid merge, platform union) */
UPDATE trends SET
    post_count       = post_count + $new_count,
    last_seen_at     = $now,
    platforms        = $merged_platforms,
    lifecycle_status = $new_lifecycle,   /* only if changed (Resurfacing detection) */
    lifecycle_history = COALESCE(...) || jsonb_build_array(...),
    centroid         = $merged_centroid::vector  /* only if computable */
WHERE trend_id = $1
```

Then calls `_reassign_and_update_posts()` and `_recompute_post_count()` exactly as `write_cluster_to_db` does.

### [write_safe_posts_to_db(posts)](../../../../layers/analysis/db/queries.py#L485)

Marks out-of-scope or isolated LOW posts as processed without creating a trends row.

```sql
UPDATE posts
SET gate4_category = 'LOW'
WHERE post_id = $post_id AND platform = $platform
  AND gate4_category IS NULL
```

### [insert_early_warning_signal(...)](../../../../layers/analysis/db/queries.py#L516)

Stores a lone high-value post as a pending early-warning signal. A partial unique index prevents duplicate insertions for the same `post_id`.

```sql
INSERT INTO trend_signals (
    signal_type, signal_data, search_platforms, search_status
) VALUES (
    'early_warning',
    jsonb_build_object(
        'post_id', $1, 'platform', $2, 'caption_text', $3,
        'intent', $4, 'embedding', $5::jsonb
    ),
    $6::jsonb, 'pending'
)
ON CONFLICT ((signal_data->>'post_id')) WHERE signal_type = 'early_warning'
DO NOTHING
```

### [mark_early_warnings_promoted(signal_ids)](../../../../layers/analysis/db/queries.py#L587)

Flips consumed early-warning signals after they have been promoted to a full cluster.

```sql
UPDATE trend_signals
SET search_status = 'promoted'
WHERE signal_id = ANY($1)
```

### [update_trend_velocity_monitor(...)](../../../../layers/analysis/db/queries.py#L652)

Updates velocity fields after each monitoring check. Called by the Monitoring layer.

```sql
UPDATE trends SET
    post_count           = post_count + $1,
    velocity_growth_rate = $2,
    velocity_check_count = velocity_check_count + 1,
    should_monitor       = should_monitor AND NOT $3
WHERE trend_id = $4
```

---

## 3. Tables Written and Read

| Table | Read | Written | Notes |
|---|---|---|---|
| `posts` | [fetch_unprocessed_posts](../../../../layers/analysis/db/queries.py#L15) | [_reassign_and_update_posts](../../../../layers/analysis/db/queries.py#L142), [write_safe_posts_to_db](../../../../layers/analysis/db/queries.py#L485) | Source of input; also updated with `gate4_category` and `linked_trend_id` |
| `trends` | [find_nearest_trend](../../../../layers/analysis/db/queries.py#L62), [merge_posts_into_trend](../../../../layers/analysis/db/queries.py#L389) | [write_cluster_to_db](../../../../layers/analysis/db/queries.py#L255), [merge_posts_into_trend](../../../../layers/analysis/db/queries.py#L389), [update_trend_velocity_monitor](../../../../layers/analysis/db/queries.py#L652) | Main output table |
| `trend_signals` | [fetch_pending_early_warnings](../../../../layers/analysis/db/queries.py#L560) | [insert_early_warning_signal](../../../../layers/analysis/db/queries.py#L516), [mark_early_warnings_promoted](../../../../layers/analysis/db/queries.py#L587) | Early-warning accumulator |
| `agent_runs` | | [create_agent_run](../../../../layers/analysis/db/queries.py#L197), [complete_agent_run](../../../../layers/analysis/db/queries.py#L214) | Run audit log |
