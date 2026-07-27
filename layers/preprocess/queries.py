import json
from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import Json

from layers.shared.db import get_connection
from layers.shared.sbert_utils import deserialize


def _parse_ts(value: str | None) -> datetime | None:
  if not value:
    return None
  return datetime.fromisoformat(value.replace("Z", "+00:00"))

def fetch_active_anchors(sources: list[str] | None = None) -> list[tuple[str, list[float]]]:
  with get_connection() as conn:
    with conn.cursor() as cur:
      if sources:
        cur.execute(
          """
            SELECT anchor_text, embedding::text
            FROM sbert_anchors
            WHERE active = TRUE AND source = ANY(%s)
            ORDER BY anchor_id
          """,
          (sources,)
        )
      else:
        cur.execute(
          """
            SELECT anchor_text, embedding::text
            FROM sbert_anchors
            WHERE active = TRUE
            ORDER BY anchor_id
          """
        )
      rows = cur.fetchall()
  return [(text, deserialize(emb)) for text, emb in rows]


def upsert_creator(creator_id: str | None, platform: str) -> None:
  if not creator_id:
    return
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
        """
          INSERT INTO creators (creator_id, platform)
          VALUES (%s, %s)
          ON CONFLICT (creator_id, platform) DO NOTHING
        """,
        (creator_id, platform),
      )


def insert_post(post: dict[str, Any], sbert_score: float | None = None) -> bool:
  """Insert post with ON CONFLICT DO NOTHING. Returns True if inserted."""
  engagement = post.get("engagement") or {}
  hashtags = post.get("hashtags")
  hashtags_value = Json(hashtags) if hashtags is not None else None
  metadata_value = Json(post.get("metadata") or {})

  upsert_creator(post.get("creator_id"), post["platform"])

  transcript = post.get("transcript_text")
  if isinstance(transcript, (list, dict)):
    transcript = json.dumps(transcript)

  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
        """
          INSERT INTO posts (
            post_id, platform, source,
            creator_id, caption_text, transcript_text, hashtags, metadata,
            likes, comments, shares, views,
            collected_at, posted_at, sbert_score
          ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s
          )
          ON CONFLICT (post_id, platform) DO NOTHING
          RETURNING post_id
        """,
        (
          post["post_id"],
          post["platform"],
          post["source"],
          post.get("creator_id"),
          post.get("caption_text"),
          transcript,
          hashtags_value,
          metadata_value,
          int(engagement.get("likes") or 0),
          int(engagement.get("comments") or 0),
          int(engagement.get("shares") or 0),
          int(engagement.get("views") or 0),
          _parse_ts(post.get("collected_at")) or datetime.now(timezone.utc),
          _parse_ts(post.get("posted_at")),
          sbert_score,
        ),
      )
      return cur.fetchone() is not None


def update_sbert_score(post_id: str, platform: str, score: float) -> None:
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
        """
          UPDATE posts SET sbert_score = %s
          WHERE post_id = %s AND platform = %s
        """,
        (score, post_id, platform),
      )


def merge_post_metadata(post_id: str, platform: str, new_metadata: dict[str, Any]) -> None:
  if not new_metadata:
    return
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
        """
          UPDATE posts 
          SET metadata = metadata || %s::jsonb
          WHERE post_id = %s AND platform = %s
        """,
        (Json(new_metadata), post_id, platform),
      )
