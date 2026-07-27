import logging

from psycopg2.extras import Json
from layers.shared.trend_utils import make_trend_id

from layers.shared.db import get_connection

logger = logging.getLogger(__name__)


def check_if_trend_exists(trend_name: str) -> bool:
  """Check if a trend with this exact derived ID already exists in the database."""
  trend_id = make_trend_id(trend_name)
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute("SELECT 1 FROM active_trends WHERE trend_id = %s", (trend_id,))
      return cur.fetchone() is not None


def fetch_unprocessed_posts(threshold: float = 0.38) -> list[dict]:
  """Fetch posts that passed SBERT filtering but haven't been classified by the agent yet."""
  with get_connection() as conn:
    with conn.cursor() as cur:
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


def write_cluster_to_db(cluster_json: dict) -> None:
  """Persist the cluster classification into the database."""
  trend_name = cluster_json.get("trend", {}).get("trend_name", "unknown_trend")
  trend_id = make_trend_id(trend_name)

  classification = cluster_json.get("classification", {})
  label = classification.get("label", "SAFE")
  risk_score = classification.get("risk_score", 0.0)

  trend = cluster_json.get("trend", {})
  post_count = trend.get("post_count", 0)
  platforms = trend.get("platforms", [])

  posts = cluster_json.get("posts", [])

  # Set gate4_relevant to TRUE if label is HARMFUL or CONCERNING, else FALSE
  gate4_relevant = True if label in ["HARMFUL", "CONCERNING"] else False

  with get_connection() as conn:
    with conn.cursor() as cur:
      # 1. Insert into active_trends
      cur.execute(
        """
          INSERT INTO active_trends (trend_id, label, risk_score, post_count, platforms, verification_status, lifecycle_status)
          VALUES (%s, %s, %s, %s, %s, 'confirmed', 'emergence')
          ON CONFLICT (trend_id) DO UPDATE
          SET post_count = active_trends.post_count + EXCLUDED.post_count,
              risk_score = GREATEST(active_trends.risk_score, EXCLUDED.risk_score)
        """,
        (trend_id, label, risk_score, post_count, Json(platforms)),
      )

      # 2. Log lifecycle event
      cur.execute(
        """
          INSERT INTO trend_lifecycle_history (trend_id, event_type, to_status, notes)
          VALUES (%s, 'discovery', 'emergence', %s)
        """,
        (trend_id, f"Trend '{trend_name}' discovered and classified as {label}"),
      )

      # 3. Update posts
      for p in posts:
        cur.execute(
          """
            UPDATE posts
            SET gate4_relevant = %s, gate4_category = %s, linked_trend_id = %s
            WHERE post_id = %s AND platform = %s
          """,
          (gate4_relevant, label, trend_id, p.get("post_id"), p.get("platform")),
        )
