import { NextResponse } from "next/server"
import pool from "@/lib/db"

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const { rows } = await pool.query(`
      SELECT
        TO_CHAR(DATE(COALESCE(t.last_seen_at, t.first_detected_at) AT TIME ZONE 'UTC'), 'YYYY-MM-DD') AS date,
        COUNT(*) FILTER (WHERE t.label = 'HIGH') AS harmful,
        COUNT(*) FILTER (WHERE t.label = 'MODERATE') AS concerning,
        COUNT(*) FILTER (WHERE t.label = 'LOW') AS safe
      FROM trends t
      WHERE COALESCE(t.last_seen_at, t.first_detected_at) >= NOW() - INTERVAL '90 days'
      GROUP BY DATE(COALESCE(t.last_seen_at, t.first_detected_at) AT TIME ZONE 'UTC')
      ORDER BY date
    `)
    return NextResponse.json({ chart_data: rows })
  } catch (err) {
    console.error("Failed to fetch chart data:", err)
    return NextResponse.json({ error: "Failed to fetch chart data" }, { status: 500 })
  }
}
