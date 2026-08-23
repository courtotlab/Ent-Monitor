"use client"

import * as React from "react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"

import { useIsMobile } from "@/hooks/use-mobile"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"

import { fetchDashboardChart, type ChartDataPoint } from "@/lib/api"

const chartConfig = {
  harmful: {
    label: "High",
    color: "#ef4444",
  },
  concerning: {
    label: "Moderate",
    color: "#eab308",
  },
  safe: {
    label: "Low",
    color: "#22c55e",
  },
} satisfies ChartConfig

export function ChartAreaInteractive() {
  const isMobile = useIsMobile()
  const [timeRange, setTimeRange] = React.useState("7d")

  React.useEffect(() => {
    if (isMobile) {
      setTimeRange("7d")
    }
  }, [isMobile])

  const [chartData, setChartData] = React.useState<ChartDataPoint[]>([])

  React.useEffect(() => {
    async function loadData() {
      try {
        const data = await fetchDashboardChart()
        setChartData(data)
      } catch (error) {
        console.error("Failed to fetch chart data", error)
      }
    }
    loadData()
  }, [])

  const filteredData = React.useMemo(() => {
    let endDateStr = new Date().toISOString().split('T')[0]
    if (chartData.length > 0) {
      endDateStr = chartData[chartData.length - 1].date.split('T')[0]
    }
    
    let daysToSubtract = 90
    if (timeRange === "30d") {
      daysToSubtract = 30
    } else if (timeRange === "7d") {
      daysToSubtract = 7
    }
    
    const endDate = new Date(`${endDateStr}T00:00:00`)
    const startDate = new Date(endDate)
    startDate.setDate(startDate.getDate() - daysToSubtract)
    
    const dataMap = new Map(chartData.map(item => [item.date.split('T')[0], item]))
    
    const result = []
    for (let d = new Date(startDate); d <= endDate; d.setDate(d.getDate() + 1)) {
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      const dateStr = `${y}-${m}-${day}`
      
      if (dataMap.has(dateStr)) {
        result.push(dataMap.get(dateStr))
      } else {
        result.push({
          date: dateStr,
          harmful: 0,
          concerning: 0,
          safe: 0
        })
      }
    }
    
    return result
  }, [chartData, timeRange])

  return (
    <Card className="@container/card">
      <CardHeader>
        <CardTitle>Trend Clusters</CardTitle>
        <CardDescription>
          <span className="hidden @[540px]/card:block">
            Active topic clusters grouped by risk level
          </span>
          <span className="@[540px]/card:hidden">Risk Levels</span>
        </CardDescription>
        <CardAction>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="outline" size="sm" className="w-40 justify-between" />}>
              {timeRange === "90d"
                ? "Last 3 months"
                : timeRange === "30d"
                ? "Last 30 days"
                : "Last 7 days"}
              <svg
                width="15"
                height="15"
                viewBox="0 0 15 15"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="h-4 w-4 opacity-50"
              >
                <path
                  d="M3.13523 6.15803C3.3241 5.95657 3.64052 5.94637 3.84197 6.13523L7.5 9.56464L11.158 6.13523C11.3595 5.94637 11.6759 5.95657 11.8648 6.15803C12.0536 6.35949 12.0434 6.67591 11.842 6.86477L7.84197 10.6148C7.64964 10.7951 7.35036 10.7951 7.15803 10.6148L3.15803 6.86477C2.95657 6.67591 2.94637 6.35949 3.13523 6.15803Z"
                  fill="currentColor"
                  fillRule="evenodd"
                  clipRule="evenodd"
                ></path>
              </svg>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-40 rounded-xl" align="end">
              <DropdownMenuItem className="rounded-lg" onClick={() => setTimeRange("90d")}>
                Last 3 months
              </DropdownMenuItem>
              <DropdownMenuItem className="rounded-lg" onClick={() => setTimeRange("30d")}>
                Last 30 days
              </DropdownMenuItem>
              <DropdownMenuItem className="rounded-lg" onClick={() => setTimeRange("7d")}>
                Last 7 days
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        <ChartContainer
          config={chartConfig}
          className="aspect-auto h-[300px] w-full"
        >
          <AreaChart data={filteredData}>
            <defs>
              <linearGradient id="fillHarmful" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="var(--color-harmful)"
                  stopOpacity={0.8}
                />
                <stop
                  offset="95%"
                  stopColor="var(--color-harmful)"
                  stopOpacity={0.1}
                />
              </linearGradient>
              <linearGradient id="fillConcerning" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="var(--color-concerning)"
                  stopOpacity={0.8}
                />
                <stop
                  offset="95%"
                  stopColor="var(--color-concerning)"
                  stopOpacity={0.1}
                />
              </linearGradient>
              <linearGradient id="fillSafe" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="var(--color-safe)"
                  stopOpacity={0.8}
                />
                <stop
                  offset="95%"
                  stopColor="var(--color-safe)"
                  stopOpacity={0.1}
                />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} />
            <YAxis hide domain={[0, (dataMax: number) => Math.max(dataMax, 1)]} />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={32}
              tickFormatter={(value) => {
                const date = new Date(value)
                return date.toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })
              }}
            />
            <ChartTooltip
              cursor={false}
              isAnimationActive={false}
              content={
                <ChartTooltipContent
                  labelFormatter={(value) => {
                    if (!value) return ""
                    return new Date(value as string | number).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })
                  }}
                  indicator="dot"
                />
              }
            />
            <Area
              dataKey="harmful"
              type="monotone"
              fill="url(#fillHarmful)"
              stroke="var(--color-harmful)"
              strokeWidth={2}
              stackId="a"
            />
            <Area
              dataKey="concerning"
              type="monotone"
              fill="url(#fillConcerning)"
              stroke="var(--color-concerning)"
              strokeWidth={2}
              stackId="a"
            />
            <Area
              dataKey="safe"
              type="monotone"
              fill="url(#fillSafe)"
              stroke="var(--color-safe)"
              strokeWidth={2}
              stackId="a"
            />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
