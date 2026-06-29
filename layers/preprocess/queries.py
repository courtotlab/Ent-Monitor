import json
from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import Json

from layers.shared.db import get_connection


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_vector(raw) -> list[float]:
    if isinstance(raw, list):
        return [float(x) for x in raw]
    text = str(raw).strip("[]")
    return [float(x) for x in text.split(",") if x.strip()]


def fetch_active_anchors() -> list[tuple[str, list[float]]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT anchor_text, embedding::text
                FROM sbert_anchors
                WHERE active = TRUE AND review_status = 'approved'
                ORDER BY anchor_id
                """
            )
            rows = cur.fetchall()
    return [(text, _parse_vector(emb)) for text, emb in rows]


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

    upsert_creator(post.get("creator_id"), post["platform"])

    transcript = post.get("transcript_text")
    if isinstance(transcript, (list, dict)):
        transcript = json.dumps(transcript)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO posts (
                    post_id, platform, source, context,
                    creator_id, caption_text, ocr_text, transcript_text, hashtags,
                    likes, comments, shares, views,
                    collected_at, posted_at, sbert_score
                ) VALUES (
                    %s, %s, %s, %s,
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
                    post["context"],
                    post.get("creator_id"),
                    post.get("caption_text"),
                    post.get("ocr_text"),
                    transcript,
                    hashtags_value,
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
