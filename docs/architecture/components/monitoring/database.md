# Monitoring Layer Database Operations

- **Locations:** [jobs/velocity_monitor.py](../../../../jobs/velocity_monitor.py), [jobs/lifecycle_monitor.py](../../../../jobs/lifecycle_monitor.py), and [layers/analysis/db/queries.py](../../../../layers/analysis/db/queries.py)
- **Component Overview:** [Monitoring Component Overview](overview.md)
- **Authoritative Schema:** For complete table schemas, constraints, and pgvector types for `trends`, see [Database Schema Reference](../../../database/schema.md).

---

## Target Tables Summary

| Table | Operation | Invoked By | Purpose |
|---|---|---|---|
| `trends` | `SELECT` | Velocity Monitor (`jobs/velocity_monitor.py`) | Fetch active trends flagged `should_monitor = TRUE` with centroid and slang terms |
| `trends` | `UPDATE` | Velocity Monitor (`jobs/velocity_monitor.py`) | Increment post counts, record hourly growth rate, update check count, and clear flag |
| `trends` | `SELECT` | Lifecycle Monitor (`jobs/lifecycle_monitor.py`) | Fetch non-latent trends to evaluate silence duration against transition thresholds |
| `trends` | `UPDATE` | Lifecycle Monitor (`jobs/lifecycle_monitor.py`) | Transition `lifecycle_status` (`Declining`, `Latent`) and append to `lifecycle_history` JSONB |

---

## 1. Velocity Monitor Database Operations

The velocity monitor runs at 17:00 and 22:00 UTC (5h and 10h post-analysis) to measure spread velocity for newly identified high/moderate risk trends.

### Read: `fetch_trends_to_monitor()`

Fetches all trends eligible for automated spread tracking.

- **Function:** `fetch_trends_to_monitor() -> list[dict]` in `layers/analysis/db/queries.py`
- **Called by:** `jobs/velocity_monitor.py:run_velocity_monitor()`

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
  AND (last_seen_at IS NULL OR last_seen_at >= NOW() - INTERVAL '14 days');
```

**Selection Criteria:**
- `should_monitor = TRUE`: Flagged by the LangGraph DECIDE node or burst logic.
- `slang_terms`: Must have at least 1 keyword for Apify search.
- `centroid IS NOT NULL`: Required for SBERT centroid cosine similarity gating.
- `label IN ('HIGH', 'MODERATE')`: Low-risk and dismissed trends are never monitored.
- Age cap: Trends with no activity for >14 days are excluded.

### Write: `update_trend_velocity_monitor()`

Updates velocity metrics on the trend after each search pass.

- **Function:** `update_trend_velocity_monitor(trend_id, new_posts_count, growth_rate, deactivate) -> None` in `layers/analysis/db/queries.py`
- **Called by:** `jobs/velocity_monitor.py:run_velocity_monitor()`

```sql
UPDATE trends SET
  post_count           = post_count + %s,
  velocity_growth_rate = %s,
  velocity_check_count = velocity_check_count + 1,
  should_monitor       = should_monitor AND NOT %s
WHERE trend_id = %s;
```

**Key Behavior:**
- `post_count`: Incremented by the number of SBERT-verified matching posts collected in this check.
- `velocity_growth_rate`: Set to `matched_posts / hours_elapsed` (posts per hour).
- `velocity_check_count`: Incremented by 1.
- `should_monitor`: Set to `FALSE` when `deactivate = True` (triggered either after 2 completed checks or when the trend exceeds 14 days of age).

---

## 2. Lifecycle Monitor Database Operations

The lifecycle monitor runs daily at midnight (00:00 UTC) to transition stale trends down the lifecycle decay curve.

### Read: `fetch_candidate_trends()`

Fetches all trends that are not yet marked `Latent`.

- **Function:** `fetch_candidate_trends() -> list[dict]` in `jobs/lifecycle_monitor.py`
- **Called by:** `jobs/lifecycle_monitor.py:run_lifecycle_monitor()`

```sql
SELECT trend_id, trend_name, lifecycle_status, last_seen_at, lifecycle_history
FROM trends
WHERE lifecycle_status NOT IN ('Latent')
ORDER BY last_seen_at ASC NULLS FIRST;
```

### Write: `update_lifecycle()`

Updates the trend's lifecycle stage and appends a timestamped entry to its audit history.

- **Function:** `update_lifecycle(trend_id: str, new_status: str, history: list) -> None` in `jobs/lifecycle_monitor.py`
- **Called by:** `jobs/lifecycle_monitor.py:run_lifecycle_monitor()`

```sql
UPDATE trends
SET lifecycle_status = %s,
    lifecycle_history = %s::jsonb
WHERE trend_id = %s;
```

**History JSONB Format:**
```json
[
  {"date": "2026-08-20T12:00:00+00:00", "status": "Emergence"},
  {"date": "2026-08-25T12:00:00+00:00", "status": "Growth"},
  {"date": "2026-09-08T00:00:00+00:00", "status": "Declining"},
  {"date": "2026-09-29T00:00:00+00:00", "status": "Latent"}
]
```

**Transition Rules Enforced:**
- `Declining` -> `Latent` if `days_since(last_seen_at) >= 21`.
- `Emergence` / `Growth` / `Resurfacing` -> `Declining` if `days_since(last_seen_at) >= 14`.
- `Isolated incident` -> skips `Declining` and transitions directly to `Latent` after 21 days.
