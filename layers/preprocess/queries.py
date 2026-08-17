import json
from datetime import UTC, datetime
from typing import Any

from psycopg2.extras import Json

from layers.shared.db import get_connection
from layers.shared.embedding import deserialize


def _parse_ts(value: str | None) -> datetime | None:
  if not value:
    return None
  return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_active_anchors(sources: list[str] | None = None) -> list[tuple[int, str, list[float]]]:
  """Fetch active SBERT anchors.

  Returns a list of (anchor_id, anchor_text, embedding) triples.
  anchor_id is used to track which anchor fired for each post.
  """
  with get_connection() as conn, conn.cursor() as cur:
    if sources:
      cur.execute(
        """
          SELECT anchor_id, anchor_text, embedding::text
          FROM sbert_anchors
          WHERE active = TRUE AND source = ANY(%s)
          ORDER BY anchor_id
        """,
        (sources,)
      )
    else:
      cur.execute(
        """
          SELECT anchor_id, anchor_text, embedding::text
          FROM sbert_anchors
          WHERE active = TRUE
          ORDER BY anchor_id
        """
      )
    rows = cur.fetchall()
  return [(anchor_id, text, deserialize(emb)) for anchor_id, text, emb in rows]


def increment_anchor_match_counts(anchor_ids: list[int]) -> None:
  """Increment match_count for each anchor that pulled in at least one passing post this batch.

  Takes a list of anchor IDs (may contain duplicates - one per matched post).
  """
  if not anchor_ids:
    return
  with get_connection() as conn, conn.cursor() as cur:
    # Batch-update: count occurrences in Python, then UPDATE per anchor
    counts: dict[int, int] = {}
    for aid in anchor_ids:
      if aid is not None:
        counts[aid] = counts.get(aid, 0) + 1
    for anchor_id, count in counts.items():
      cur.execute(
        """
          UPDATE sbert_anchors
          SET match_count = match_count + %s
          WHERE anchor_id = %s
        """,
        (count, anchor_id),
      )


def upsert_creator(creator_id: str | None, platform: str) -> None:
  if not creator_id:
    return
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
        INSERT INTO creators (creator_id, platform)
        VALUES (%s, %s)
        ON CONFLICT (creator_id, platform) DO NOTHING
      """,
      (creator_id, platform),
    )


def insert_post(
  post: dict[str, Any],
  sbert_score: float | None = None,
  matched_anchor_id: int | None = None,
) -> bool:
  """Insert post with ON CONFLICT DO NOTHING. Returns True if inserted."""
  engagement = post.get("engagement") or {}
  hashtags = post.get("hashtags")
  hashtags_value = Json(hashtags) if hashtags is not None else None
  metadata_value = Json(post.get("metadata") or {})

  upsert_creator(post.get("creator_id"), post["platform"])

  transcript = post.get("transcript_text")
  if isinstance(transcript, (list, dict)):
    transcript = json.dumps(transcript)

  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
        INSERT INTO posts (
          post_id, platform, source,
          creator_id, caption_text, transcript_text, hashtags, metadata,
          likes, comments, shares, views,
          collected_at, posted_at, sbert_score, matched_anchor_id
        ) VALUES (
          %s, %s, %s,
          %s, %s, %s, %s, %s,
          %s, %s, %s, %s,
          %s, %s, %s, %s
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
        _parse_ts(post.get("collected_at")) or datetime.now(UTC),
        _parse_ts(post.get("posted_at")),
        sbert_score,
        matched_anchor_id,
      ),
    )
    return cur.fetchone() is not None


def update_sbert_score(post_id: str, platform: str, score: float) -> None:
  with get_connection() as conn, conn.cursor() as cur:
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
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
        UPDATE posts 
        SET metadata = metadata || %s::jsonb
        WHERE post_id = %s AND platform = %s
      """,
      (Json(new_metadata), post_id, platform),
    )
