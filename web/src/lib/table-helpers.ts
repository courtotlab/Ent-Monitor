import type { Row } from "@tanstack/react-table"
import type { TrendData } from "@/lib/api"

export function byDateField<K extends "first_detected_at" | "last_seen_at">(key: K) {
  return (a: Row<TrendData>, b: Row<TrendData>): number => {
    const aDate = a.original[key] ? new Date(a.original[key]!).getTime() : 0
    const bDate = b.original[key] ? new Date(b.original[key]!).getTime() : 0
    return aDate - bDate
  }
}
