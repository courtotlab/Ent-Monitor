import logging
from datetime import UTC, datetime

from psycopg2.extras import Json

from layers.shared.db import get_connection
from layers.shared.trends import make_trend_id

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  Read helpers (unchanged)
# ──────────────────────────────────────────────────────────────────────────────

def check_if_trend_exists(trend_name: str) -> bool:
  """Check if a trend with this exact derived ID already exists in the database."""
  trend_id = make_trend_id(trend_name)
  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute("SELECT 1 FROM active_trends WHERE trend_id = %s", (trend_id,))
      return cur.fetchone() is not None
  except Exception as exc:
    logger.warning("Database unavailable (%s) — defaulting is_known_trend to False", exc)
    return False


def fetch_unprocessed_posts(threshold: float = 0.38) -> list[dict]:
  """Fetch posts that passed SBERT filtering but haven't been classified by the agent yet."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
        SELECT post_id, platform, caption_text, sbert_score, creator_id, likes, views, posted_at
        FROM posts
        WHERE sbert_score >= %s
        AND gate4_relevant IS NULL
      """,
      (threshold,),
    )
    rows = cur.fetchall()

    posts = []
    for row in rows:
      post_id, platform, caption_text, sbert_score, creator_id, likes, views, posted_at = row
      posts.append(
        {
          "post_id": post_id,
          "platform": platform,
          "caption_text": caption_text,
          "sbert_score": sbert_score,
          "creator_id": creator_id,
          "likes": likes,
          "views": views,
          "posted_at": posted_at.isoformat() if posted_at else None,
        }
      )
    return posts


def fetch_existing_trend_centroids() -> list[dict]:
  """Fetch all active trends that have a centroid stored.

  Returns a list of dicts with keys:
    trend_id, label, search_context, centroid (list[float]), post_count
  Used by OBSERVE to match new clusters against existing DB trends.
  """
  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
          SELECT trend_id, label, search_context, centroid::text, post_count
          FROM active_trends
          WHERE centroid IS NOT NULL
            AND false_positive = FALSE
        """
      )
      rows = cur.fetchall()
      results = []
      for trend_id, label, search_context, centroid_str, post_count in rows:
        # pgvector returns centroid as '[0.1,0.2,...]' string
        if centroid_str:
          centroid_vals = [float(x) for x in centroid_str.strip('[]').split(',')]
        else:
          continue
        results.append({
          "trend_id": trend_id,
          "label": label,
          "search_context": search_context or "",
          "centroid": centroid_vals,
          "post_count": post_count or 0,
        })
      logger.info("DB: fetched %d existing trend centroids", len(results))
      return results
  except Exception as exc:
    logger.warning("DB: failed to fetch trend centroids — %s", exc)
    return []


# ──────────────────────────────────────────────────────────────────────────────
#  Agent run tracking
# ──────────────────────────────────────────────────────────────────────────────

def create_agent_run(run_id: str, posts_input: int) -> None:
  """Insert a new agent_runs row with status 'running'."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
          INSERT INTO agent_runs (run_id, started_at, status, posts_input)
          VALUES (%s, NOW(), 'running', %s)
          ON CONFLICT (run_id) DO NOTHING
        """,
        (run_id, posts_input),
      )
    logger.info("DB: created agent_run %s (posts_input=%d)", run_id, posts_input)
  except Exception as exc:
    logger.warning("DB: failed to create agent_run %s — %s", run_id, exc)


def complete_agent_run(
  run_id: str,
  cluster_results: list[dict],
  status: str = "completed",
  error_message: str | None = None,
) -> None:
  """Finalise the agent_runs row with duration, counts, and optional report summary."""
  try:
    # Build a compact markdown report from cluster results
    report_lines = []
    trends_classified = 0
    for r in cluster_results:
      c = r.get("classification", {})
      label = c.get("label", "?")
      risk = c.get("risk_score", 0.0)
      name = r.get("trend", {}).get("trend_name", r.get("cluster_id", "?"))
      report_lines.append(f"- **{name}**: {label} (risk {risk:.2f})")
      trends_classified += 1

    report_md = "\n".join(report_lines) if report_lines else None

    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
          UPDATE agent_runs
          SET completed_at      = NOW(),
              duration_seconds  = EXTRACT(EPOCH FROM (NOW() - started_at)),
              status            = %s,
              clusters_formed   = %s,
              trends_classified = %s,
              report_markdown   = %s,
              error_message     = %s
          WHERE run_id = %s
        """,
        (
          status,
          len(cluster_results),
          trends_classified,
          report_md,
          error_message,
          run_id,
        ),
      )
    logger.info("DB: completed agent_run %s — status=%s, clusters=%d", run_id, status, len(cluster_results))
  except Exception as exc:
    logger.warning("DB: failed to complete agent_run %s — %s", run_id, exc)


# ──────────────────────────────────────────────────────────────────────────────
#  Cluster → DB persistence (HARMFUL / CONCERNING clusters)
# ──────────────────────────────────────────────────────────────────────────────

def write_cluster_to_db(cluster_json: dict) -> None:
  """Persist the cluster classification into active_trends and posts tables.

  Handles both new trend discovery and merging into existing trends:
  - UPSERT into active_trends (increment post_count, take max risk_score, merge platforms)
  - Store/update centroid and search_context for cross-run matching
  - Log lifecycle event (discovery for new, post_update for existing)
  - Update posts with gate4_relevant, gate4_category, linked_trend_id
  - If a post was previously linked to a different trend, decrement that trend's post_count
  """
  trend_data = cluster_json.get("trend", {})
  trend_name = trend_data.get("trend_name", "unknown_trend")
  matched_trend_id = trend_data.get("matched_trend_id")
  trend_id = matched_trend_id if matched_trend_id else make_trend_id(trend_name)

  classification = cluster_json.get("classification", {})
  label = classification.get("label", "SAFE")
  risk_score = classification.get("risk_score", 0.0)

  post_count = trend_data.get("post_count", 0)
  platforms = trend_data.get("platforms", [])

  posts = cluster_json.get("posts", [])
  centroid = cluster_json.get("centroid")  # list[float] or None
  search_context = cluster_json.get("search_context", "")

  # HARMFUL/CONCERNING → gate4_relevant TRUE; SAFE → FALSE
  gate4_relevant = label in ("HARMFUL", "CONCERNING")

  # Format centroid for pgvector: '[0.1,0.2,...]' or None
  centroid_str = None
  if centroid and isinstance(centroid, (list, tuple)) and len(centroid) > 0:
    centroid_str = '[' + ','.join(str(v) for v in centroid) + ']'

  now = datetime.now(UTC)

  try:
    with get_connection() as conn, conn.cursor() as cur:
      # ── 1. Check if trend already exists ──
      cur.execute("SELECT trend_id, post_count, centroid::text FROM active_trends WHERE trend_id = %s", (trend_id,))
      existing = cur.fetchone()
      is_new_trend = existing is None

      if not is_new_trend and existing[2] and centroid:
        # Existing centroid found, compute weighted average in Python
        existing_post_count = existing[1] or 0
        existing_centroid_vals = [float(x) for x in existing[2].strip('[]').split(',')]
        if len(existing_centroid_vals) == len(centroid):
          merged_centroid = []
          total_posts = existing_post_count + post_count
          if total_posts > 0:
            for i in range(len(centroid)):
              val = (existing_centroid_vals[i] * existing_post_count + centroid[i] * post_count) / total_posts
              merged_centroid.append(val)
            centroid_str = '[' + ','.join(str(v) for v in merged_centroid) + ']'

      # ── 2. UPSERT into active_trends (including centroid + search_context) ──
      cur.execute(
        """
          INSERT INTO active_trends
            (trend_id, label, risk_score, post_count, platforms,
             verification_status, lifecycle_status, first_detected_at, last_seen_at,
             search_context, centroid)
          VALUES (%s, %s, %s, %s, %s, 'confirmed', 'emergence', %s, %s, %s, %s::vector)
          ON CONFLICT (trend_id) DO UPDATE SET
            post_count  = active_trends.post_count + EXCLUDED.post_count,
            risk_score  = GREATEST(active_trends.risk_score, EXCLUDED.risk_score),
            label       = CASE
                            WHEN EXCLUDED.label = 'HARMFUL' THEN 'HARMFUL'
                            WHEN EXCLUDED.label = 'CONCERNING' AND active_trends.label != 'HARMFUL' THEN 'CONCERNING'
                            ELSE active_trends.label
                          END,
            platforms   = (
                            SELECT COALESCE(jsonb_agg(DISTINCT elem), '[]'::jsonb)
                            FROM (
                              SELECT jsonb_array_elements_text(active_trends.platforms) AS elem
                              UNION
                              SELECT jsonb_array_elements_text(EXCLUDED.platforms) AS elem
                            ) combined
                          ),
            last_seen_at    = EXCLUDED.last_seen_at,
            search_context  = COALESCE(EXCLUDED.search_context, active_trends.search_context),
            centroid        = COALESCE(EXCLUDED.centroid, active_trends.centroid)
        """,
        (trend_id, label, risk_score, post_count, Json(platforms), now, now,
         search_context or None, centroid_str),
      )

      # ── 3. Log lifecycle event ──
      if is_new_trend:
        event_type = "discovery"
        notes = f"Trend '{trend_name}' discovered and classified as {label}"
      else:
        event_type = "post_update"
        notes = f"Merged {post_count} new posts into trend '{trend_name}' (label: {label})"

      cur.execute(
        """
          INSERT INTO trend_lifecycle_history
            (trend_id, event_type, to_status, post_count_at_event, triggered_by, notes)
          VALUES (%s, %s, %s, %s, 'analysis_agent', %s)
        """,
        (
          trend_id,
          event_type,
          "emergence" if is_new_trend else None,
          post_count,
          notes,
        ),
      )

      # ── 4. Update posts — handle re-assignment from old trends ──
      for p in posts:
        p_id = p.get("post_id")
        p_platform = p.get("platform")
        if not p_id or not p_platform:
          continue

        # Check if post was previously linked to a different trend
        cur.execute(
          "SELECT linked_trend_id FROM posts WHERE post_id = %s AND platform = %s",
          (p_id, p_platform),
        )
        row = cur.fetchone()
        if row and row[0] and row[0] != trend_id:
          # Decrement old trend's post_count
          old_trend_id = row[0]
          cur.execute(
            """
              UPDATE active_trends
              SET post_count = GREATEST(post_count - 1, 0)
              WHERE trend_id = %s
            """,
            (old_trend_id,),
          )

        # Set the new classification
        cur.execute(
          """
            UPDATE posts
            SET gate4_relevant  = %s,
                gate4_category  = %s,
                linked_trend_id = %s
            WHERE post_id = %s AND platform = %s
          """,
          (gate4_relevant, label, trend_id, p_id, p_platform),
        )

    logger.info(
      "DB: wrote cluster → trend %s (%s, %s) — %d posts, is_new=%s",
      trend_id, trend_name, label, len(posts), is_new_trend,
    )
  except Exception as exc:
    logger.error("DB: failed to write cluster to DB — %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
#  SAFE cluster post updates (no active_trends row needed)
# ──────────────────────────────────────────────────────────────────────────────

def write_safe_posts_to_db(posts: list[dict]) -> None:
  """Mark posts from SAFE clusters as gate4_relevant=FALSE in the database.

  SAFE clusters don't create active_trends rows, but their posts still need
  gate4_relevant/gate4_category set so they aren't re-processed in future runs.
  """
  if not posts:
    return

  try:
    with get_connection() as conn, conn.cursor() as cur:
      for p in posts:
        p_id = p.get("post_id")
        p_platform = p.get("platform")
        if not p_id or not p_platform:
          continue

        cur.execute(
          """
            UPDATE posts
            SET gate4_relevant  = FALSE,
                gate4_category  = 'SAFE'
            WHERE post_id = %s AND platform = %s
              AND gate4_relevant IS NULL
          """,
          (p_id, p_platform),
        )
    logger.info("DB: marked %d posts as SAFE", len(posts))
  except Exception as exc:
    logger.warning("DB: failed to mark SAFE posts — %s", exc)

