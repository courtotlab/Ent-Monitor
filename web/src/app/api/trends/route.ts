import { NextResponse } from "next/server"
import pool from "@/lib/db"

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const { rows } = await pool.query(`
      SELECT 
        trend_id, label, risk_score, post_count,
        COALESCE(platforms, '[]'::jsonb) AS platforms,
        lifecycle_status,
        first_detected_at, last_seen_at,
        trend_name, abstract, verification_status,
        discovery_source, velocity_growth_rate,
        COALESCE(slang_terms, '[]'::jsonb) AS slang_terms
      FROM trends
      ORDER BY last_seen_at DESC NULLS LAST, first_detected_at DESC
    `)
    return NextResponse.json({ trends: rows })
  } catch (err) {
    console.error("Failed to fetch trends:", err)
    return NextResponse.json({ error: "Failed to fetch trends" }, { status: 500 })
  }
}
