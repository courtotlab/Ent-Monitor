import type { RiskLevel } from "./utils"
import type { LifecycleStatus, VerificationStatus } from "./constants"

const API_BASE = "/api"

// Response types

export interface DashboardStats {
  harmful_count: number
  concerning_count: number
  total_trends_classified: number
  active_creators: number
}

export interface ChartDataPoint {
  date: string
  harmful: number
  concerning: number
  safe: number
}

export interface TrendData {
  trend_id: string
  label: RiskLevel
  risk_score: number
  post_count: number
  platforms: string[]
  lifecycle_status: LifecycleStatus
  first_detected_at: string | null
  last_seen_at: string | null
  trend_name: string | null
  abstract: string | null
  verification_status: VerificationStatus
  discovery_source: string | null
  velocity_growth_rate?: number | null
  should_monitor?: boolean
  evidence?: { url: string; title: string; source: string; pmid: string | null }[]
  harm_mechanism?: string | null
  lifecycle_history?: { date: string; status: LifecycleStatus; post_count: number }[]
  slang_terms?: string[] | null
}

export interface PostData {
  post_id: string
  platform: string
  creator_id: string | null
  caption_text: string | null
  url: string | null
  likes: number
  comments: number
  shares: number
  views: number
  collected_at: string
  posted_at: string | null
  sbert_score: number | null
}

export interface TrendDetails {
  trend: TrendData
  posts: PostData[]
  chart_data: { date: string; count: number }[]
}

// Fetch helpers

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    throw new Error(`API ${path} responded ${res.status}: ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  return apiFetch<DashboardStats>("/dashboard/stats")
}

export async function fetchDashboardChart(): Promise<ChartDataPoint[]> {
  const data = await apiFetch<{ chart_data: ChartDataPoint[] }>("/dashboard/chart")
  return data.chart_data
}

export async function fetchRecentTrends(): Promise<TrendData[]> {
  const data = await apiFetch<{ trends: TrendData[] }>("/dashboard/recent-trends")
  return data.trends
}

export async function fetchAllTrends(): Promise<TrendData[]> {
  const data = await apiFetch<{ trends: TrendData[] }>("/trends")
  return data.trends
}

export async function fetchTrendDetails(trendId: string): Promise<TrendDetails> {
  return apiFetch<TrendDetails>(`/trends/${trendId}/details`)
}
