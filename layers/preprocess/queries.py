import json
from datetime import UTC, datetime


from psycopg2.extras import Json, execute_values
from layers.ingestion.shared.models import RawPostDict

from layers.shared.db import get_connection
from layers.shared.embedding import deserialize

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
  """Increment match_count for each anchor that pulled in at least one passing post this batch."""
  if not anchor_ids:
    return
  with get_connection() as conn, conn.cursor() as cur:
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


def fetch_unprocessed_posts(limit: int = 100000) -> list[RawPostDict]:
  """Fetch posts that haven't been preprocessed (sbert_score IS NULL)."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
      SELECT post_id, platform, source, creator_id, caption_text, transcript_text,
             hashtags, metadata, likes, comments, shares, views,
             collected_at, posted_at
      FROM posts
      WHERE sbert_score IS NULL
      LIMIT %s
      """,
      (limit,),
    )
    cols = [desc[0] for desc in cur.description]
    posts = []
    for row in cur.fetchall():
        post_dict = dict(zip(cols, row))
        post_dict["engagement"] = {
            "likes": post_dict.pop("likes"),
            "comments": post_dict.pop("comments"),
            "shares": post_dict.pop("shares"),
            "views": post_dict.pop("views"),
        }
        if post_dict["collected_at"]: post_dict["collected_at"] = post_dict["collected_at"].isoformat()
        if post_dict["posted_at"]: post_dict["posted_at"] = post_dict["posted_at"].isoformat()
        posts.append(post_dict)
    return posts


def update_preprocessed_posts(updates: list[tuple[str, str, float, int | None]]) -> None:
  """Batch update sbert_score and matched_anchor_id.
  Updates is a list of (post_id, platform, sbert_score, matched_anchor_id).
  """
  if not updates:
    return
  with get_connection() as conn, conn.cursor() as cur:
    execute_values(
        cur,
        """
        UPDATE posts
        SET sbert_score = data.sbert_score::real,
            matched_anchor_id = data.matched_anchor_id::integer
        FROM (VALUES %s) AS data (post_id, platform, sbert_score, matched_anchor_id)
        WHERE posts.post_id = data.post_id AND posts.platform = data.platform
        """,
        updates,
    )
