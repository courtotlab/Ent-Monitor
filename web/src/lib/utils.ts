import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export type RiskLevel = "HIGH" | "MODERATE" | "LOW"

export function parseUtcDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const safe = iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`
  return new Date(safe)
}

export function pluralize(n: number, singular: string, plural = `${singular}s`): string {
  return `${n} ${n === 1 ? singular : plural}`
}

export function formatDate(iso: string | null | undefined) {
  const d = parseUtcDate(iso)
  if (!d) return "-"
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })
}

export function formatShortDate(iso: string | null | undefined, opts: { withYear?: boolean } = {}): string {
  const d = parseUtcDate(iso)
  if (!d) return "-"
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: opts.withYear ? "numeric" : undefined, timeZone: "UTC" })
}

export function formatTrendName(trendId: string) {
  return trendId
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
