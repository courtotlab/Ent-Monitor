"""API route handlers queries the PostgreSQL database directly."""

import logging

from fastapi import APIRouter, HTTPException
import psycopg2.extras

from layers.shared.db import get_connection

logger = logging.getLogger(__name__)
router = APIRouter()


# Dashboard Stats 
@router.get("/dashboard/stats")
def get_dashboard_stats():
  """Aggregated stats for the dashboard cards."""
  try:
    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
      cur.execute("""
        SELECT
          (SELECT COUNT(*) FROM trends WHERE label = 'HIGH') AS harmful_count,
          (SELECT COUNT(*) FROM trends WHERE label = 'MODERATE') AS concerning_count,
          (SELECT COUNT(*) FROM trends) AS total_trends_classified,
          (SELECT COUNT(*) FROM creators) AS active_creators
      """)
      return cur.fetchone()
  except Exception as exc:
    logger.error("Failed to fetch dashboard stats: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))


# Dashboard Chart                     

@router.get("/dashboard/chart")
def get_dashboard_chart():
  """Daily harmful vs concerning post counts for the area chart (last 90 days)."""
  try:
    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
      cur.execute(
        """
        SELECT
          DATE(COALESCE(t.last_seen_at, t.first_detected_at) AT TIME ZONE 'UTC') AS date,
          COUNT(*) FILTER (WHERE t.label = 'HIGH') AS harmful,
          COUNT(*) FILTER (WHERE t.label = 'MODERATE') AS concerning,
          COUNT(*) FILTER (WHERE t.label = 'LOW') AS safe
        FROM trends t
        WHERE COALESCE(t.last_seen_at, t.first_detected_at) >= NOW() - INTERVAL '90 days'
        GROUP BY DATE(COALESCE(t.last_seen_at, t.first_detected_at) AT TIME ZONE 'UTC')
        ORDER BY date
        """
      )
      return {"chart_data": cur.fetchall()}
  except Exception as exc:
    logger.error("Failed to fetch chart data: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))


# Dashboard Recent Trends

@router.get("/dashboard/recent-trends")
def get_dashboard_recent_trends():
  """Top 10 most recently classified or re-emerged trends for the dashboard."""
  try:
    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
      cur.execute(
        """
        SELECT trend_id, label, risk_score, post_count, COALESCE(platforms, '[]'::jsonb) AS platforms,
               lifecycle_status,
               first_detected_at, last_seen_at,
               trend_name, abstract, verification_status, discovery_source,
               velocity_growth_rate
        FROM trends
        ORDER BY GREATEST(first_detected_at, COALESCE(last_seen_at, first_detected_at)) DESC
        LIMIT 10
        """
      )
      return {"trends": cur.fetchall()}
  except Exception as exc:
    logger.error("Failed to fetch recent trends: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))


# Trends                        

@router.get("/trends")
def get_trends():
  """All active trends for the trends table."""
  try:
    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
      cur.execute(
        """
        SELECT trend_id, label, risk_score, post_count, COALESCE(platforms, '[]'::jsonb) AS platforms,
               lifecycle_status,
               first_detected_at, last_seen_at,
               trend_name, abstract, verification_status,
               discovery_source, velocity_growth_rate
        FROM trends
        ORDER BY last_seen_at DESC NULLS LAST, first_detected_at DESC
        """
      )
      return {"trends": cur.fetchall()}
  except Exception as exc:
    logger.error("Failed to fetch trends: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))


# Trend Details

@router.get("/trends/{trend_id}/details")
def get_trend_details(trend_id: str):
  """Get full details for a specific trend, including its posts and volume chart data."""
  try:
    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
      # 1. Fetch trend
      cur.execute(
        """
        SELECT trend_id, label, risk_score, post_count, COALESCE(platforms, '[]'::jsonb) AS platforms,
               lifecycle_status,
               first_detected_at, last_seen_at,
               trend_name, abstract, verification_status,
               discovery_source, velocity_growth_rate, COALESCE(evidence, '[]'::jsonb) AS evidence
        FROM trends
        WHERE trend_id = %s
        """,
        (trend_id,)
      )
      trend = cur.fetchone()
      if not trend:
        raise HTTPException(status_code=404, detail="Trend not found")
      
      # 2. Fetch posts
      cur.execute(
        """
        SELECT post_id, platform, creator_id, caption_text, COALESCE(metadata, '{}'::jsonb) AS metadata, likes, comments, shares, views,
               collected_at, posted_at, sbert_score
        FROM posts
        WHERE linked_trend_id = %s
        ORDER BY collected_at DESC
        """,
        (trend_id,)
      )
      posts = cur.fetchall()
      
      # 3. Fetch chart data (daily volume)
      cur.execute(
        """
        SELECT DATE(COALESCE(posted_at, collected_at) AT TIME ZONE 'UTC') AS date, COUNT(*) AS count
        FROM posts
        WHERE linked_trend_id = %s
        GROUP BY DATE(COALESCE(posted_at, collected_at) AT TIME ZONE 'UTC')
        ORDER BY date ASC
        """,
        (trend_id,)
      )
      chart_data = cur.fetchall()
        
      return {
        "trend": trend,
        "posts": posts,
        "chart_data": chart_data
      }
  except HTTPException:
    raise
  except Exception as exc:
    logger.error("Failed to fetch trend details: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))
