import json
from datetime import UTC, datetime

from psycopg2.extras import Json
from layers.ingestion.shared.models import RawPostDict

from layers.shared.db import get_connection
from layers.shared.embedding import deserialize


def fetch_sbert_anchors_with_source(sources: list[str] | None = None) -> list[tuple[int, str, list[float]]]:
  """Fetch active SBERT anchors with their source for ingestion filters."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute("SELECT anchor_id, embedding, source FROM sbert_anchors WHERE active = TRUE AND source = ANY(%s)", (sources,)) if sources else cur.execute("SELECT anchor_id, embedding, source FROM sbert_anchors WHERE active = TRUE")
    return [(a, s, deserialize(e)) for a, e, s in cur.fetchall()]


def _parse_ts(value: str | None) -> datetime | None:
  if not value:
    return None
  return datetime.fromisoformat(value.replace("Z", "+00:00"))

def insert_post(
  post: RawPostDict,
  sbert_score: float | None = None,
  matched_anchor_id: int | None = None,
) -> bool:
  """Insert post with ON CONFLICT DO NOTHING. Returns True if inserted."""
  engagement = post.get("engagement") or {}
  url = post.get("url") or ""

  transcript = post.get("transcript_text")
  if isinstance(transcript, (list, dict)):
    transcript = json.dumps(transcript)

  VALID_SOURCES = {
    "creator_monitor",
    "engager",
    "reddit",
    "explore_feed",
    "gtrends_search",
    "gdelt_news",
  }
  post_source = post.get("source")
  if post_source not in VALID_SOURCES:
    post_source = "explore_feed"

  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
   INSERT INTO posts (
    post_id, platform, source,
    creator_id, caption_text, transcript_text, url,
    likes, comments, shares, views,
    collected_at, posted_at, sbert_score, matched_anchor_id
   ) VALUES (
    %s, %s, %s,
    (SELECT creator_id FROM creators WHERE creator_id = %s AND platform = %s), %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s, %s
   )
   ON CONFLICT (post_id, platform) DO UPDATE SET
    source = COALESCE(EXCLUDED.source, posts.source),
    creator_id = COALESCE(EXCLUDED.creator_id, posts.creator_id),
    caption_text = COALESCE(EXCLUDED.caption_text, posts.caption_text),
    transcript_text = COALESCE(EXCLUDED.transcript_text, posts.transcript_text),
    url = COALESCE(EXCLUDED.url, posts.url),
    likes = GREATEST(COALESCE(EXCLUDED.likes, 0), COALESCE(posts.likes, 0)),
    comments = GREATEST(COALESCE(EXCLUDED.comments, 0), COALESCE(posts.comments, 0)),
    shares = GREATEST(COALESCE(EXCLUDED.shares, 0), COALESCE(posts.shares, 0)),
    views = GREATEST(COALESCE(EXCLUDED.views, 0), COALESCE(posts.views, 0)),
    collected_at = EXCLUDED.collected_at,
    posted_at = COALESCE(EXCLUDED.posted_at, posts.posted_at),
    matched_anchor_id = CASE
     WHEN EXCLUDED.sbert_score IS NOT NULL AND (posts.sbert_score IS NULL OR EXCLUDED.sbert_score > posts.sbert_score) THEN EXCLUDED.matched_anchor_id
     ELSE posts.matched_anchor_id
    END,
    sbert_score = CASE
     WHEN EXCLUDED.sbert_score IS NOT NULL AND (posts.sbert_score IS NULL OR EXCLUDED.sbert_score > posts.sbert_score) THEN EXCLUDED.sbert_score
     ELSE posts.sbert_score
    END
   RETURNING (xmax = 0) AS is_insert
   """,
      (
        post["post_id"],
        post["platform"],
        post_source,
        post.get("creator_id"),
        post["platform"],
        post.get("caption_text"),
        transcript,
        url,
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
    result = cur.fetchone()
    return result[0] if result else False


def get_recent_gt_spikes(trend_titles: list[str]) -> set[str]:
  """Get previously processed GTrends spikes to avoid deduplication."""
  if not trend_titles:
    return set()
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
   SELECT search_query FROM trend_signals
   WHERE search_query = ANY(%s)
    AND signal_type = 'gt_spike'
    AND dismissed = FALSE
    AND detected_at >= NOW() - INTERVAL '7 days'
   """,
      (trend_titles,),
    )
    return {row[0] for row in cur.fetchall()}


def insert_gt_spike(signal_data: Json, search_query: str, linked_trend_id: str) -> None:
  """Insert a new GTrends spike into trend_signals."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
   INSERT INTO trends (trend_id, trend_name, label, risk_score, discovery_source)
   VALUES (%s, %s, 'MODERATE', 0.5, 'gtrends_search')
   ON CONFLICT DO NOTHING
   """,
      (linked_trend_id, search_query),
    )
    cur.execute(
      """
   INSERT INTO trend_signals (
    signal_type, signal_data,
    search_query, search_platforms, search_status, linked_trend_id
   ) VALUES (
    'gt_spike', %s,
    %s, '["tiktok","instagram"]'::jsonb, 'pending', %s
   )
   """,
      (signal_data, search_query, linked_trend_id),
    )


def get_gdelt_last_polled_url() -> str | None:
  """Fetch the last GDELT GKG URL we successfully processed."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute("SELECT state_value->>'last_url' FROM pipeline_state WHERE state_key = 'gdelt_poll'")
    return r[0] if (r := cur.fetchone()) else None


def update_gdelt_last_polled_url(url: str) -> None:
  """Update the last GDELT GKG URL in the pipeline state."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
   UPDATE pipeline_state 
   SET state_value = jsonb_build_object('last_url', %s, 'last_polled_at', NOW()), 
    updated_at = NOW() 
   WHERE state_key = 'gdelt_poll'
   """,
      (url,),
    )


def get_recent_gdelt_seen_urls() -> set[str]:
  """Fetch recently processed GDELT URLs to prevent re-processing."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      "SELECT url FROM gdelt_seen_articles WHERE seen_at >= NOW() - INTERVAL '48 hours'"
    )
    return {row[0] for row in cur.fetchall()}


def upsert_gdelt_seen_url(url: str) -> None:
  """Mark a GDELT URL as seen."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
   INSERT INTO gdelt_seen_articles (url, seen_at)
   VALUES (%s, NOW())
   ON CONFLICT (url) DO UPDATE SET seen_at = NOW()
   """,
      (url,),
    )


def insert_news_trend_signal(signal_data: Json, search_query: str) -> None:
  """Insert a new trend signal from GDELT news."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
   INSERT INTO trend_signals (
    signal_type, signal_data,
    search_query, search_platforms,
    search_status, detected_at
   ) VALUES (
    'news_match', %s,
    %s, '["tiktok","instagram"]', 'pending', NOW()
   )
   ON CONFLICT DO NOTHING
   """,
      (signal_data, search_query),
    )
