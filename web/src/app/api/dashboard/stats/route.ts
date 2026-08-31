import { NextResponse } from "next/server"
import pool from "@/lib/db"

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const { rows } = await pool.query(`
      SELECT
        (SELECT COUNT(*) FROM trends WHERE label = 'HIGH') AS harmful_count,
        (SELECT COUNT(*) FROM trends WHERE label = 'MODERATE') AS concerning_count,
        (SELECT COUNT(*) FROM trends) AS total_trends_classified,
        (SELECT COUNT(*) FROM creators) AS active_creators
    `)
    return NextResponse.json(rows[0])
  } catch (err) {
    console.error("Failed to fetch dashboard stats:", err)
    return NextResponse.json({ error: "Failed to fetch dashboard stats" }, { status: 500 })
  }
}
