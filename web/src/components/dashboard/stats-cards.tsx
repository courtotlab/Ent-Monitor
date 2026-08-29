"use client"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  AlertTriangleIcon,
  AlertCircleIcon,
  ShieldCheckIcon,
  ActivityIcon,
} from "lucide-react"
import { fetchDashboardStats, type DashboardStats } from "@/lib/api"
import { useApi } from "@/hooks/use-api"
import { pluralize } from "@/lib/utils"

export function StatsCards() {
  const { data: stats, loading, error } = useApi<DashboardStats>(fetchDashboardStats)

  if (error) {
    return (
      <div className="px-4 lg:px-6">
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load dashboard stats. Is the API server running?
        </div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:bg-linear-to-t *:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card *:data-[slot=card]:shadow-xs lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4 dark:*:data-[slot=card]:bg-card">
      <Card className="@container/card gap-2">
        <CardHeader>
          <CardDescription>High Risk Trends</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {loading || !stats ? (
              <span className="inline-block h-8 w-12 animate-pulse rounded bg-muted" />
            ) : (
              stats.harmful_count
            )}
          </CardTitle>
          <CardAction>
            <Badge variant="destructive" className="bg-destructive/10 text-destructive hover:bg-destructive/20 border-0">
              <AlertTriangleIcon className="mr-1 h-3 w-3" />
              High Risk
            </Badge>
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="line-clamp-1 flex gap-2 font-medium">Requires immediate attention</div>
          <div className="text-muted-foreground">
            {loading || !stats ? "Loading…" : `${pluralize(stats.harmful_count, "trend")} classified as High Risk`}
          </div>
        </CardFooter>
      </Card>

      <Card className="@container/card gap-2">
        <CardHeader>
          <CardDescription>Moderate Risk Trends</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {loading || !stats ? (
              <span className="inline-block h-8 w-12 animate-pulse rounded bg-muted" />
            ) : (
              stats.concerning_count
            )}
          </CardTitle>
          <CardAction>
            <Badge className="bg-amber-500/10 text-amber-600 hover:bg-amber-500/20 border-0 dark:text-amber-400">
              <AlertCircleIcon className="mr-1 h-3 w-3" />
              Monitor
            </Badge>
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="line-clamp-1 flex gap-2 font-medium">Under active monitoring</div>
          <div className="text-muted-foreground">
            {loading || !stats ? "Loading…" : `${pluralize(stats.concerning_count, "trend")} flagged as Moderate Risk`}
          </div>
        </CardFooter>
      </Card>

      <Card className="@container/card gap-2">
        <CardHeader>
          <CardDescription>Trends Classified</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {loading || !stats ? (
              <span className="inline-block h-8 w-12 animate-pulse rounded bg-muted" />
            ) : (
              stats.total_trends_classified
            )}
          </CardTitle>
          <CardAction>
            <Badge variant="outline" className="bg-green-500/10 text-green-600 hover:bg-green-500/20 border-0 dark:text-green-400">
              <ShieldCheckIcon className="mr-1 h-3 w-3" />
              Verified
            </Badge>
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="line-clamp-1 flex gap-2 font-medium">All trends classified to date</div>
          <div className="text-muted-foreground">
            {loading || !stats ? "Loading…" : `Across all lifecycle stages`}
          </div>
        </CardFooter>
      </Card>

      <Card className="@container/card gap-2">
        <CardHeader>
          <CardDescription>Active Creators</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {loading || !stats ? (
              <span className="inline-block h-8 w-12 animate-pulse rounded bg-muted" />
            ) : (
              stats.active_creators.toLocaleString()
            )}
          </CardTitle>
          <CardAction>
            <Badge variant="outline" className="bg-purple-500/10 text-purple-600 hover:bg-purple-500/20 border-0 dark:text-purple-400">
              <ActivityIcon className="mr-1 h-3 w-3" />
              Influencers
            </Badge>
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="line-clamp-1 flex gap-2 font-medium">Unique voices driving trends</div>
          <div className="text-muted-foreground">
            {loading || !stats ? "Loading…" : "Across all monitored platforms"}
          </div>
        </CardFooter>
      </Card>
    </div>
  )
}
