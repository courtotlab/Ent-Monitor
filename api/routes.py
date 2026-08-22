"""API route handlers queries the PostgreSQL database directly."""

import json
import logging

from fastapi import APIRouter, HTTPException

from layers.shared.db import get_connection

logger = logging.getLogger(__name__)
router = APIRouter()


# Dashboard Stats 
@router.get("/dashboard/stats")
def get_dashboard_stats():
  """Aggregated stats for the dashboard cards."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      # 1. High risk trends count
      cur.execute(
        "SELECT COUNT(*) FROM trends WHERE label = 'HIGH'"
      )
      harmful_count = cur.fetchone()[0]

      # 2. Moderate risk trends count
      cur.execute(
        "SELECT COUNT(*) FROM trends WHERE label = 'MODERATE'"
      )
      concerning_count = cur.fetchone()[0]

      # 3. Total trends classified (all non-false-positive trends)
      cur.execute(
        "SELECT COUNT(*) FROM trends"
      )
      total_trends_classified = cur.fetchone()[0]

      # 4. Active creators monitored (non-retired)
      cur.execute(
        "SELECT COUNT(*) FROM creators WHERE tier != 'retired'"
      )
      active_creators = cur.fetchone()[0]

      return {
        "harmful_count": harmful_count,
        "concerning_count": concerning_count,
        "total_trends_classified": total_trends_classified,
        "active_creators": active_creators,
      }
  except Exception as exc:
    logger.error("Failed to fetch dashboard stats: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))


# Dashboard Chart                     

@router.get("/dashboard/chart")
def get_dashboard_chart():
  """Daily harmful vs concerning post counts for the area chart (last 90 days)."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
        SELECT
          DATE(COALESCE(t.last_seen_at, t.first_detected_at)) AS day,
          COUNT(*) FILTER (WHERE t.label = 'HIGH') AS harmful_trends,
          COUNT(*) FILTER (WHERE t.label = 'MODERATE') AS concerning_trends,
          COUNT(*) FILTER (WHERE t.label = 'LOW') AS safe_trends
        FROM trends t
        WHERE COALESCE(t.last_seen_at, t.first_detected_at) >= NOW() - INTERVAL '90 days'
        GROUP BY DATE(COALESCE(t.last_seen_at, t.first_detected_at))
        ORDER BY day
        """
      )
      rows = cur.fetchall()

      data = []
      for row in rows:
        data.append({
          "date": row[0].isoformat(),
          "harmful": row[1],
          "concerning": row[2],
          "safe": row[3],
        })

      return {"chart_data": data}
  except Exception as exc:
    logger.error("Failed to fetch chart data: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))


# Dashboard Recent Trends

@router.get("/dashboard/recent-trends")
def get_dashboard_recent_trends():
  """Top 10 most recently classified or re-emerged trends for the dashboard."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
        SELECT trend_id, label, risk_score, post_count, platforms,
               lifecycle_status,
               first_detected_at, last_seen_at,
               trend_name, abstract, verification_status, discovery_source,
               velocity_growth_rate, velocity_checked_at
        FROM trends
        ORDER BY GREATEST(first_detected_at, COALESCE(last_seen_at, first_detected_at)) DESC
        LIMIT 10
        """
      )
      rows = cur.fetchall()

      trends = []
      for row in rows:
        platforms_raw = row[4]
        if isinstance(platforms_raw, str):
          platforms_raw = json.loads(platforms_raw)
        elif platforms_raw is None:
          platforms_raw = []

        trends.append({
          "trend_id": row[0],
          "label": row[1],
          "risk_score": row[2],
          "post_count": row[3],
          "platforms": platforms_raw,
          "lifecycle_status": row[5],
          "first_detected_at": row[6].isoformat() if row[6] else None,
          "last_seen_at": row[7].isoformat() if row[7] else None,
          "trend_name": row[8],
          "abstract": row[9],
          "verification_status": row[10],
          "discovery_source": row[11],
          "velocity_growth_rate": row[12],
          "velocity_checked_at": row[13].isoformat() if row[13] else None,
        })

      return {"trends": trends}
  except Exception as exc:
    logger.error("Failed to fetch recent trends: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))


# Trends                        

@router.get("/trends")
def get_trends():
  """All active trends for the trends table."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
        SELECT trend_id, label, risk_score, post_count, platforms,
               lifecycle_status,
               first_detected_at, last_seen_at,
               trend_name, abstract, verification_status,
               discovery_source, velocity_growth_rate, velocity_checked_at
        FROM trends
        ORDER BY last_seen_at DESC NULLS LAST, first_detected_at DESC
        """
      )
      rows = cur.fetchall()

      trends = []
      for row in rows:
        platforms_raw = row[4]
        if isinstance(platforms_raw, str):
          platforms_raw = json.loads(platforms_raw)
        elif platforms_raw is None:
          platforms_raw = []

        trends.append({
          "trend_id": row[0],
          "label": row[1],
          "risk_score": row[2],
          "post_count": row[3],
          "platforms": platforms_raw,
          "lifecycle_status": row[5],
          "first_detected_at": row[6].isoformat() if row[6] else None,
          "last_seen_at": row[7].isoformat() if row[7] else None,
          "trend_name": row[8],
          "abstract": row[9],
          "verification_status": row[10],
          "discovery_source": row[11],
          "velocity_growth_rate": row[12],
          "velocity_checked_at": row[13].isoformat() if row[13] else None,
        })

      return {"trends": trends}
  except Exception as exc:
    logger.error("Failed to fetch trends: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))


# Trend Details

@router.get("/trends/{trend_id}/details")
def get_trend_details(trend_id: str):
  """Get full details for a specific trend, including its posts and volume chart data."""
  try:
    with get_connection() as conn, conn.cursor() as cur:
      # 1. Fetch trend
      cur.execute(
        """
        SELECT trend_id, label, risk_score, post_count, platforms,
               lifecycle_status,
               first_detected_at, last_seen_at,
               trend_name, abstract, verification_status,
               discovery_source, velocity_growth_rate, velocity_checked_at, evidence
        FROM trends
        WHERE trend_id = %s
        """,
        (trend_id,)
      )
      trend_row = cur.fetchone()
      if not trend_row:
        raise HTTPException(status_code=404, detail="Trend not found")
      
      platforms_raw = trend_row[4]
      if isinstance(platforms_raw, str):
        platforms_raw = json.loads(platforms_raw)
      elif platforms_raw is None:
        platforms_raw = []
        
      trend = {
        "trend_id": trend_row[0],
        "label": trend_row[1],
        "risk_score": trend_row[2],
        "post_count": trend_row[3],
        "platforms": platforms_raw,
        "lifecycle_status": trend_row[5],
        "first_detected_at": trend_row[6].isoformat() if trend_row[6] else None,
        "last_seen_at": trend_row[7].isoformat() if trend_row[7] else None,
        "trend_name": trend_row[8],
        "abstract": trend_row[9],
        "verification_status": trend_row[10],
        "discovery_source": trend_row[11],
        "velocity_growth_rate": trend_row[12],
        "velocity_checked_at": trend_row[13].isoformat() if trend_row[13] else None,
        "evidence": trend_row[14] if isinstance(trend_row[14], list) else (json.loads(trend_row[14]) if isinstance(trend_row[14], str) else (trend_row[14] or []))
      }
      
      # 2. Fetch posts
      cur.execute(
        """
        SELECT post_id, platform, creator_id, caption_text, metadata, likes, comments, shares, views,
               collected_at, posted_at, sbert_score
        FROM posts
        WHERE linked_trend_id = %s
        ORDER BY collected_at DESC
        """,
        (trend_id,)
      )
      posts_rows = cur.fetchall()
      posts = []
      for prow in posts_rows:
        meta = prow[4]
        if isinstance(meta, str):
          meta = json.loads(meta)
        elif meta is None:
          meta = {}
          
        posts.append({
          "post_id": prow[0],
          "platform": prow[1],
          "creator_id": prow[2],
          "caption_text": prow[3],
          "metadata": meta,
          "likes": prow[5],
          "comments": prow[6],
          "shares": prow[7],
          "views": prow[8],
          "collected_at": prow[9].isoformat() if prow[9] else None,
          "posted_at": prow[10].isoformat() if prow[10] else None,
          "sbert_score": prow[11]
        })
        
      # 3. Fetch chart data (daily volume)
      cur.execute(
        """
        SELECT DATE(collected_at) AS day, COUNT(*)
        FROM posts
        WHERE linked_trend_id = %s
        GROUP BY DATE(collected_at)
        ORDER BY day
        """,
        (trend_id,)
      )
      chart_rows = cur.fetchall()
      chart_data = []
      for crow in chart_rows:
        chart_data.append({
          "date": crow[0].isoformat(),
          "count": crow[1]
        })
        
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
