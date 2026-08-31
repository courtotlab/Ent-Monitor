import { NextResponse } from "next/server"
import pool from "@/lib/db"

export const dynamic = 'force-dynamic'

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params

  try {
    // 1. Fetch trend
    const trendResult = await pool.query(
      `
      SELECT 
        trend_id, label, risk_score, post_count,
        COALESCE(platforms, '[]'::jsonb) AS platforms,
        lifecycle_status,
        first_detected_at, last_seen_at,
        trend_name, abstract, verification_status,
        discovery_source, velocity_growth_rate, should_monitor,
        COALESCE(evidence, '[]'::jsonb) AS evidence,
        harm_mechanism,
        COALESCE(lifecycle_history, '[]'::jsonb) AS lifecycle_history,
        COALESCE(slang_terms, '[]'::jsonb) AS slang_terms
      FROM trends
      WHERE trend_id = $1
      `,
      [id]
    )

    if (trendResult.rows.length === 0) {
      return NextResponse.json({ error: "Trend not found" }, { status: 404 })
    }

    // 2. Fetch posts linked to this trend
    const postsResult = await pool.query(
      `
      SELECT 
        post_id, platform, creator_id, caption_text, url,
        likes, comments, shares, views,
        collected_at, posted_at, sbert_score
      FROM posts
      WHERE linked_trend_id = $1
      ORDER BY collected_at DESC
      `,
      [id]
    )

    // 3. Fetch daily volume chart data
    const chartResult = await pool.query(
      `
      SELECT 
        TO_CHAR(DATE(COALESCE(posted_at, collected_at) AT TIME ZONE 'UTC'), 'YYYY-MM-DD') AS date,
        COUNT(*) AS count
      FROM posts
      WHERE linked_trend_id = $1
      GROUP BY DATE(COALESCE(posted_at, collected_at) AT TIME ZONE 'UTC')
      ORDER BY date ASC
      `,
      [id]
    )

    return NextResponse.json({
      trend: trendResult.rows[0],
      posts: postsResult.rows,
      chart_data: chartResult.rows,
    })
  } catch (err) {
    console.error("Failed to fetch trend details:", err)
    return NextResponse.json({ error: "Failed to fetch trend details" }, { status: 500 })
  }
}
