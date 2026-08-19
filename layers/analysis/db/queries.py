import json
import math
import logging
from datetime import UTC, datetime

from psycopg2.extras import Json

from layers.shared.db import get_connection
from layers.shared.trends import make_trend_id

logger = logging.getLogger(__name__)

VELOCITY_TRIGGER_THRESHOLD = 5  # posts/hour to activate velocity tracking


# Read helpers

def check_if_trend_exists(trend_id: str) -> bool:
  """Check if a trend with this exact derived ID already exists in the database."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute("SELECT 1 FROM trends WHERE trend_id = %s", (trend_id,))
      return cur.fetchone() is not None
  except Exception as exc:
    logger.warning("Database unavailable (%s) defaulting is_known_trend to False", exc)
    return False


def fetch_unprocessed_posts(threshold: float = 0.38) -> list[dict]:
  """Fetch posts that passed SBERT filtering but haven't been classified by the agent yet."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
        SELECT post_id, platform, caption_text, sbert_score, creator_id,
               likes, views, posted_at, matched_anchor_id
        FROM posts
        WHERE sbert_score >= %s
        AND gate4_category IS NULL
      """,
      (threshold,),
    )
    rows = cur.fetchall()

    posts = []
    for row in rows:
      post_id, platform, caption_text, sbert_score, creator_id, likes, views, posted_at, matched_anchor_id = row
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
          "matched_anchor_id": matched_anchor_id,
        }
      )
    return posts


def find_nearest_trend(centroid: list[float], threshold: float = 0.95) -> dict | None:
  """Use pgvector HNSW index to find the closest DB trend to a centroid.

  Returns the matched trend dict or None if nothing above threshold.
  Uses cosine distance operator (<=>): distance = 1 - cosine_similarity.
  """
  if not centroid or len(centroid) == 0:
    return None

  distance_threshold = 1.0 - threshold
  centroid_str = '[' + ','.join(str(v) for v in centroid) + ']'

  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
          SELECT trend_id, label, risk_score, search_context, post_count,
                 lifecycle_status, verification_status, last_seen_at,
                 1 - (centroid <=> %s::vector) AS similarity
          FROM trends
          WHERE centroid IS NOT NULL
            AND (centroid <=> %s::vector) < %s
          ORDER BY centroid <=> %s::vector
          LIMIT 1
        """,
        (centroid_str, centroid_str, distance_threshold, centroid_str),
      )
      row = cur.fetchone()
      if row is None:
        return None

      return {
        "trend_id": row[0],
        "label": row[1],
        "risk_score": row[2],
        "search_context": row[3] or "",
        "post_count": row[4] or 0,
        "lifecycle_status": row[5],
        "verification_status": row[6],
        "last_seen_at": row[7].isoformat() if row[7] else None,
        "similarity": row[8],
      }
  except Exception as exc:
    logger.warning("DB: pgvector KNN query failed - %s", exc)
    return None


# Shared Helpers

def _merge_centroids(existing_centroid_text: str | None, existing_count: int, new_centroid: list[float] | None, new_count: int) -> str | None:
  if not existing_centroid_text or not new_centroid or len(new_centroid) == 0:
    return None
  
  existing_vals = [float(x) for x in existing_centroid_text.strip('[]').split(',')]
  if len(existing_vals) != len(new_centroid):
    return None
    
  total = existing_count + new_count
  if total <= 0:
    return None
    
  merged = [(existing_vals[i] * existing_count + new_centroid[i] * new_count) / total for i in range(len(new_centroid))]
  
  norm = math.sqrt(sum(x * x for x in merged))
  if norm > 0:
    merged = [x / norm for x in merged]
    
  return '[' + ','.join(str(v) for v in merged) + ']'

def _check_resurfacing(trend_id: str, lifecycle: str, last_seen: datetime | None) -> str:
  if not last_seen:
    return lifecycle
  days_since_last = (datetime.now(UTC) - last_seen).days
  if days_since_last > 14 and lifecycle not in ("Emergence",):
    logger.info("DB: trend %s resurfacing after %d days of inactivity", trend_id, days_since_last)
    return "Resurfacing"
  return lifecycle

def _reassign_and_update_posts(cur, posts: list[dict], trend_id: str, label: str) -> None:
  for p in posts:
    p_id = p.get("post_id")
    p_platform = p.get("platform")
    if not p_id or not p_platform:
      continue

    cur.execute(
      "SELECT linked_trend_id FROM posts WHERE post_id = %s AND platform = %s",
      (p_id, p_platform),
    )
    old = cur.fetchone()
    if old and old[0] and old[0] != trend_id:
      cur.execute(
        "UPDATE trends SET post_count = GREATEST(post_count - 1, 0) WHERE trend_id = %s",
        (old[0],),
      )

    cur.execute(
      """
        UPDATE posts
        SET gate4_category  = %s,
            linked_trend_id = %s
        WHERE post_id = %s AND platform = %s
      """,
      (label, trend_id, p_id, p_platform),
    )


# Agent run tracking

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
    logger.warning("DB: failed to create agent_run %s - %s", run_id, exc)


def complete_agent_run(
  run_id: str,
  cluster_results: list[dict],
  status: str = "completed",
  error_message: str | None = None,
) -> None:
  """Finalise the agent_runs row with duration, counts, and optional report summary."""
  try:
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
    logger.info("DB: completed agent_run %s - status=%s, clusters=%d", run_id, status, len(cluster_results))
  except Exception as exc:
    logger.warning("DB: failed to complete agent_run %s - %s", run_id, exc)


# Cluster DB persistence (HARMFUL / CONCERNING clusters)

def write_cluster_to_db(cluster_json: dict, centroid: list[float] | None = None) -> None:
  """Persist the cluster classification into trends and posts tables.

  Handles both new trend discovery and merging into existing trends:
  - UPSERT into trends (increment post_count, take max risk_score, merge platforms)
  - Store/update centroid and search_context for cross-run matching
  - Log lifecycle event (discovery for new, post_update for existing)
  - Update posts with gate4_category, linked_trend_id
  - If a post was previously linked to a different trend, decrement that trend's post_count
  - Check for Resurfacing (>14 day gap since last_seen_at)
  """
  trend_data = cluster_json.get("trend", {})
  trend_name = trend_data.get("trend_name", "unknown_trend")
  matched_trend_id = trend_data.get("matched_trend_id")
  det_trend_id = trend_data.get("deterministic_trend_id")
  if matched_trend_id:
    trend_id = matched_trend_id
  elif det_trend_id:
    trend_id = det_trend_id
  else:
    trend_id = make_trend_id(trend_name)

  classification = cluster_json.get("classification", {})
  label = classification.get("label", "SAFE")
  risk_score = classification.get("risk_score", 0.0)
  slang_terms = classification.get("slang_terms", [])

  post_count = trend_data.get("post_count", 0)
  abstract = cluster_json.get("abstract", "")
  search_context = cluster_json.get("search_context", "")
  harm_mechanism = cluster_json.get("harm_mechanism", "")
  evidence_data = cluster_json.get("evidence", {})
  platforms = trend_data.get("platforms", [])

  posts = cluster_json.get("posts", [])

  centroid_str = None
  if centroid and isinstance(centroid, (list, tuple)) and len(centroid) > 0:
    centroid_str = '[' + ','.join(str(v) for v in centroid) + ']'

  now = datetime.now(UTC)

  try:
    with get_connection() as conn, conn.cursor() as cur:
      # 1. Check if trend already exists + check for Resurfacing
      cur.execute(
        "SELECT trend_id, post_count, centroid::text, last_seen_at, lifecycle_status FROM trends WHERE trend_id = %s",
        (trend_id,),
      )
      existing = cur.fetchone()
      is_new_trend = existing is None

      lifecycle = classification.get("lifecycle", "Isolated incident")
      verification = classification.get("verification", "PROVISIONAL")

      if not is_new_trend:
        lifecycle = _check_resurfacing(trend_id, lifecycle, existing[3])
        merged_centroid = _merge_centroids(existing[2], existing[1] or 0, centroid, post_count)
        if merged_centroid:
          centroid_str = merged_centroid

      # 2. UPSERT into trends
      cur.execute(
        """
          INSERT INTO trends
            (trend_id, label, risk_score, post_count, platforms, slang_terms,
             verification_status, lifecycle_status, first_detected_at, last_seen_at,
             abstract, search_context, trend_name, harm_mechanism, evidence, centroid, velocity_next_check_at, lifecycle_history)
          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector,
                  NOW() + INTERVAL '24 hours',
                  jsonb_build_array(jsonb_build_object('date', NOW(), 'status', %s, 'post_count', %s)))
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
            lifecycle_history   = COALESCE(trends.lifecycle_history, '[]'::jsonb) || 
                                  jsonb_build_array(jsonb_build_object('date', NOW(), 'status', EXCLUDED.lifecycle_status, 'post_count', trends.post_count + EXCLUDED.post_count)),
            platforms           = (
                                    SELECT COALESCE(jsonb_agg(DISTINCT elem), '[]'::jsonb)
                                    FROM (
                                      SELECT jsonb_array_elements_text(trends.platforms) AS elem
                                      UNION
                                      SELECT jsonb_array_elements_text(EXCLUDED.platforms) AS elem
                                    ) combined
                                  ),
            slang_terms         = (
                                    SELECT COALESCE(jsonb_agg(DISTINCT elem), '[]'::jsonb)
                                    FROM (
                                      SELECT jsonb_array_elements_text(trends.slang_terms) AS elem
                                      UNION
                                      SELECT jsonb_array_elements_text(EXCLUDED.slang_terms) AS elem
                                    ) combined
                                  ),
            last_seen_at        = EXCLUDED.last_seen_at,
            trend_name          = COALESCE(EXCLUDED.trend_name, trends.trend_name),
            search_context      = COALESCE(EXCLUDED.search_context, trends.search_context),
            harm_mechanism      = COALESCE(EXCLUDED.harm_mechanism, trends.harm_mechanism),
            centroid            = COALESCE(EXCLUDED.centroid, trends.centroid)
        """,
        (trend_id, label, risk_score, post_count, Json(platforms), Json(slang_terms),
         verification, lifecycle,
         now, now, abstract or None, search_context or None, trend_name or None, harm_mechanism or None, Json(evidence_data) if evidence_data else None, centroid_str,
         lifecycle, post_count),
      )


      # 4. Update posts - handle re-assignment from old trends
      _reassign_and_update_posts(cur, posts, trend_id, label)

      # 5. Check burst -> trigger velocity tracking
      _maybe_trigger_velocity(cur, trend_id)

    logger.info(
      "DB: wrote cluster -> trend %s (%s, %s) - %d posts, is_new=%s",
      trend_id, trend_name, label, len(posts), is_new_trend,
    )
  except Exception as exc:
    logger.error("DB: failed to write cluster to DB - %s", exc)


def merge_posts_into_trend(trend_id: str, posts: list[dict], new_centroid: list[float] | None = None) -> dict | None:
  """Fast-path merge: append posts to an existing trend without reclassification.

  - Increment post_count
  - Merge platforms (JSONB union)
  - Weighted-average the centroid
  - Update last_seen_at
  - Log 'post_update' in trend_lifecycle_history
  - Update each post's gate4_category, linked_trend_id
  - Check for Resurfacing (last_seen > 14 days ago)
  - Check burst -> trigger velocity tracking
  - Returns the updated trend dict
  """
  now = datetime.now(UTC)
  new_post_count = len(posts)
  new_platforms = list(set(p.get("platform", "unknown") for p in posts))

  try:
    with get_connection() as conn, conn.cursor() as cur:
      # Fetch current trend state
      cur.execute(
        """
          SELECT label, risk_score, post_count, platforms, centroid::text,
                 last_seen_at, lifecycle_status, verification_status
          FROM trends
          WHERE trend_id = %s
        """,
        (trend_id,),
      )
      row = cur.fetchone()
      if row is None:
        logger.warning("DB: merge_posts_into_trend - trend %s not found", trend_id)
        return None

      label, risk_score, existing_post_count, existing_platforms, centroid_text, last_seen, lifecycle, verification = row

      # Resurfacing detection
      new_lifecycle = _check_resurfacing(trend_id, lifecycle, last_seen)

      # Weighted centroid merge
      centroid_str = _merge_centroids(centroid_text, existing_post_count, new_centroid, new_post_count)

      # Merge platforms
      if isinstance(existing_platforms, str):
        existing_platforms = json.loads(existing_platforms)
      merged_platforms = list(set((existing_platforms or []) + new_platforms))

      # Update the trend
      update_parts = [
        "post_count = post_count + %s",
        "last_seen_at = %s",
        "platforms = %s",
      ]
      update_vals = [new_post_count, now, Json(merged_platforms)]


      if new_lifecycle != lifecycle:
        update_parts.append("lifecycle_status = %s")
        update_vals.append(new_lifecycle)
        
      update_parts.append("lifecycle_history = COALESCE(lifecycle_history, '[]'::jsonb) || jsonb_build_array(jsonb_build_object('date', NOW(), 'status', %s, 'post_count', post_count + %s))")
      update_vals.extend([new_lifecycle, new_post_count])

      if centroid_str:
        update_parts.append("centroid = %s::vector")
        update_vals.append(centroid_str)

      update_vals.append(trend_id)

      cur.execute(
        f"UPDATE trends SET {', '.join(update_parts)} WHERE trend_id = %s",
        tuple(update_vals),
      )


      # Update each post
      _reassign_and_update_posts(cur, posts, trend_id, label)

      # Check burst -> trigger velocity tracking
      _maybe_trigger_velocity(cur, trend_id)

    logger.info("DB: fast-path merged %d posts into trend %s", new_post_count, trend_id)
    return {
      "trend_id": trend_id,
      "label": label,
      "risk_score": risk_score,
      "post_count": existing_post_count + new_post_count,
      "lifecycle_status": new_lifecycle,
      "verification_status": verification,
    }
  except Exception as exc:
    logger.error("DB: fast-path merge failed for trend %s - %s", trend_id, exc)
    return None


# Velocity helpers

def _maybe_trigger_velocity(cur, trend_id: str) -> None:
  """Check if a trend is bursting (>N posts in the last hour) and schedule velocity tracking."""
  cur.execute(
    """
      SELECT COUNT(*) FROM posts
      WHERE linked_trend_id = %s
        AND collected_at >= NOW() - INTERVAL '1 hour'
    """,
    (trend_id,),
  )
  posts_last_hour = cur.fetchone()[0]
  if posts_last_hour >= VELOCITY_TRIGGER_THRESHOLD:
    cur.execute(
      """
        UPDATE trends
        SET velocity_next_check_at = NOW() + INTERVAL '3 hours'
        WHERE trend_id = %s
          AND (velocity_next_check_at IS NULL OR velocity_next_check_at > NOW() + INTERVAL '3 hours')
      """,
      (trend_id,),
    )
    logger.info("DB: velocity tracking triggered for trend %s (%d posts/hour)", trend_id, posts_last_hour)


def fetch_trends_due_for_velocity() -> list[dict]:
  """Fetch trends whose velocity_next_check_at has passed."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
          SELECT trend_id, velocity_growth_rate, velocity_checked_at,
                 lifecycle_status, post_count
          FROM trends
          WHERE velocity_next_check_at <= NOW()
        """
      )
      rows = cur.fetchall()
      return [
        {
          "trend_id": row[0],
          "prev_growth_rate": row[1],
          "last_checked_at": row[2],
          "lifecycle_status": row[3],
          "post_count": row[4],
        }
        for row in rows
      ]
  except Exception as exc:
    logger.warning("DB: failed to fetch velocity-due trends - %s", exc)
    return []


def fetch_posts_last_12h(trend_id: str) -> list[datetime]:
  """Fetch collected_at timestamps for all posts linked to a trend in the last 12 hours."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
          SELECT COALESCE(posted_at, collected_at) FROM posts
          WHERE linked_trend_id = %s
            AND COALESCE(posted_at, collected_at) >= NOW() - INTERVAL '12 hours'
          ORDER BY COALESCE(posted_at, collected_at)
        """,
        (trend_id,),
      )
      return [row[0] for row in cur.fetchall()]
  except Exception as exc:
    logger.warning("DB: failed to fetch 12h posts for %s - %s", trend_id, exc)
    return []


def update_trend_velocity(
  trend_id: str,
  growth_rate: float,
  new_lifecycle: str | None,
  next_check_hours: int = 24,
) -> None:
  """Write velocity computation results and optionally transition lifecycle."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      if new_lifecycle:
        cur.execute(
          """
            UPDATE trends
            SET velocity_growth_rate = %s,
                velocity_checked_at = NOW(),
                velocity_next_check_at = NOW() + make_interval(hours => %s),
                lifecycle_status = %s,
                lifecycle_history = COALESCE(lifecycle_history, '[]'::jsonb) || jsonb_build_array(jsonb_build_object('date', NOW(), 'status', %s, 'post_count', post_count))
            WHERE trend_id = %s
          """,
          (growth_rate, next_check_hours, new_lifecycle, new_lifecycle, trend_id),
        )
      else:
        cur.execute(
          """
            UPDATE trends
            SET velocity_growth_rate = %s,
                velocity_checked_at = NOW(),
                velocity_next_check_at = NOW() + make_interval(hours => %s)
            WHERE trend_id = %s
          """,
          (growth_rate, next_check_hours, trend_id),
        )
    logger.info("DB: velocity updated for %s - rate=%.3f, lifecycle=%s", trend_id, growth_rate, new_lifecycle)
  except Exception as exc:
    logger.warning("DB: failed to update velocity for %s - %s", trend_id, exc)


# SAFE cluster post updates (no trends row needed)

def write_safe_posts_to_db(posts: list[dict]) -> None:
  """Mark posts from SAFE clusters as gate4_category='LOW' in the database."""
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
            SET gate4_category = 'LOW'
            WHERE post_id = %s AND platform = %s
              AND gate4_category IS NULL
          """,
          (p_id, p_platform),
        )
    logger.info("DB: marked %d posts as SAFE", len(posts))
  except Exception as exc:
    logger.warning("DB: failed to mark SAFE posts - %s", exc)
