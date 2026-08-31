"use client"

import * as React from "react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"

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

import { fetchDashboardChart, type ChartDataPoint } from "@/lib/api"
import { useApi } from "@/hooks/use-api"
import { filterByTimeRange, formatChartDate, AreaGradient, type TimeRange } from "@/lib/chart-helpers"
import { TimeRangeSelect } from "@/components/shared/time-range-select"

const chartConfig = {
  harmful: { label: "High", color: "#ef4444" },
  concerning: { label: "Moderate", color: "#eab308" },
  safe: { label: "Low", color: "#22c55e" },
} satisfies ChartConfig

export function RiskChart() {
  const [timeRange, setTimeRange] = React.useState<TimeRange>("7d")
  const { data } = useApi<ChartDataPoint[]>(fetchDashboardChart)
  const chartData = React.useMemo(() => data ?? [], [data])

  const filteredData = React.useMemo(
    () => filterByTimeRange(chartData, timeRange, undefined, { harmful: 0, concerning: 0, safe: 0 }),
    [chartData, timeRange],
  )

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
          <TimeRangeSelect value={timeRange} onChange={setTimeRange} />
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-2 sm:px-6 sm:pt-4">
        <ChartContainer
          config={chartConfig}
          className="aspect-auto h-[200px] @xl/main:h-[300px] w-full"
        >
          <AreaChart data={filteredData}>
            <defs>
              <AreaGradient id="fillHarmful" colorVar="harmful" />
              <AreaGradient id="fillConcerning" colorVar="concerning" />
              <AreaGradient id="fillSafe" colorVar="safe" />
            </defs>
            <CartesianGrid vertical={false} />
            <YAxis hide domain={[0, (dataMax: number) => Math.max(dataMax, 1)]} />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={32}
              tickFormatter={formatChartDate}
            />
            <ChartTooltip
              cursor={false}
              isAnimationActive={false}
              content={
                <ChartTooltipContent
                  labelFormatter={(value) => (value ? formatChartDate(value) : "")}
                  indicator="dot"
                />
              }
            />
            <Area dataKey="harmful" type="monotone" fill="url(#fillHarmful)" stroke="var(--color-harmful)" strokeWidth={2} />
            <Area dataKey="concerning" type="monotone" fill="url(#fillConcerning)" stroke="var(--color-concerning)" strokeWidth={2} />
            <Area dataKey="safe" type="monotone" fill="url(#fillSafe)" stroke="var(--color-safe)" strokeWidth={2} />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
