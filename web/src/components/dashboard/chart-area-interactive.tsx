"use client"

import * as React from "react"
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts"

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

export const description = "An interactive area chart"

const chartData = [
  { date: "2024-04-01", views: 222, shares: 150 },
  { date: "2024-04-02", views: 97, shares: 180 },
  { date: "2024-04-03", views: 167, shares: 120 },
  { date: "2024-04-04", views: 242, shares: 260 },
  { date: "2024-04-05", views: 373, shares: 290 },
  { date: "2024-04-06", views: 301, shares: 340 },
  { date: "2024-04-07", views: 245, shares: 180 },
  { date: "2024-04-08", views: 409, shares: 320 },
  { date: "2024-04-09", views: 59, shares: 110 },
  { date: "2024-04-10", views: 261, shares: 190 },
  { date: "2024-04-11", views: 327, shares: 350 },
  { date: "2024-04-12", views: 292, shares: 210 },
  { date: "2024-04-13", views: 342, shares: 380 },
  { date: "2024-04-14", views: 137, shares: 220 },
  { date: "2024-04-15", views: 120, shares: 170 },
  { date: "2024-04-16", views: 138, shares: 190 },
  { date: "2024-04-17", views: 446, shares: 360 },
  { date: "2024-04-18", views: 364, shares: 410 },
  { date: "2024-04-19", views: 243, shares: 180 },
  { date: "2024-04-20", views: 89, shares: 150 },
  { date: "2024-04-21", views: 137, shares: 200 },
  { date: "2024-04-22", views: 224, shares: 170 },
  { date: "2024-04-23", views: 138, shares: 230 },
  { date: "2024-04-24", views: 387, shares: 290 },
  { date: "2024-04-25", views: 215, shares: 250 },
  { date: "2024-04-26", views: 75, shares: 130 },
  { date: "2024-04-27", views: 383, shares: 420 },
  { date: "2024-04-28", views: 122, shares: 180 },
  { date: "2024-04-29", views: 315, shares: 240 },
  { date: "2024-04-30", views: 454, shares: 380 },
  { date: "2024-05-01", views: 165, shares: 220 },
  { date: "2024-05-02", views: 293, shares: 310 },
  { date: "2024-05-03", views: 247, shares: 190 },
  { date: "2024-05-04", views: 385, shares: 420 },
  { date: "2024-05-05", views: 481, shares: 390 },
  { date: "2024-05-06", views: 498, shares: 520 },
  { date: "2024-05-07", views: 388, shares: 300 },
  { date: "2024-05-08", views: 149, shares: 210 },
  { date: "2024-05-09", views: 227, shares: 180 },
  { date: "2024-05-10", views: 293, shares: 330 },
  { date: "2024-05-11", views: 335, shares: 270 },
  { date: "2024-05-12", views: 197, shares: 240 },
  { date: "2024-05-13", views: 197, shares: 160 },
  { date: "2024-05-14", views: 448, shares: 490 },
  { date: "2024-05-15", views: 473, shares: 380 },
  { date: "2024-05-16", views: 338, shares: 400 },
  { date: "2024-05-17", views: 499, shares: 420 },
  { date: "2024-05-18", views: 315, shares: 350 },
  { date: "2024-05-19", views: 235, shares: 180 },
  { date: "2024-05-20", views: 177, shares: 230 },
  { date: "2024-05-21", views: 82, shares: 140 },
  { date: "2024-05-22", views: 81, shares: 120 },
  { date: "2024-05-23", views: 252, shares: 290 },
  { date: "2024-05-24", views: 294, shares: 220 },
  { date: "2024-05-25", views: 201, shares: 250 },
  { date: "2024-05-26", views: 213, shares: 170 },
  { date: "2024-05-27", views: 420, shares: 460 },
  { date: "2024-05-28", views: 233, shares: 190 },
  { date: "2024-05-29", views: 78, shares: 130 },
  { date: "2024-05-30", views: 340, shares: 280 },
  { date: "2024-05-31", views: 178, shares: 230 },
  { date: "2024-06-01", views: 178, shares: 200 },
  { date: "2024-06-02", views: 470, shares: 410 },
  { date: "2024-06-03", views: 103, shares: 160 },
  { date: "2024-06-04", views: 439, shares: 380 },
  { date: "2024-06-05", views: 88, shares: 140 },
  { date: "2024-06-06", views: 294, shares: 250 },
  { date: "2024-06-07", views: 323, shares: 370 },
  { date: "2024-06-08", views: 385, shares: 320 },
  { date: "2024-06-09", views: 438, shares: 480 },
  { date: "2024-06-10", views: 155, shares: 200 },
  { date: "2024-06-11", views: 92, shares: 150 },
  { date: "2024-06-12", views: 492, shares: 420 },
  { date: "2024-06-13", views: 81, shares: 130 },
  { date: "2024-06-14", views: 426, shares: 380 },
  { date: "2024-06-15", views: 307, shares: 350 },
  { date: "2024-06-16", views: 371, shares: 310 },
  { date: "2024-06-17", views: 475, shares: 520 },
  { date: "2024-06-18", views: 107, shares: 170 },
  { date: "2024-06-19", views: 341, shares: 290 },
  { date: "2024-06-20", views: 408, shares: 450 },
  { date: "2024-06-21", views: 169, shares: 210 },
  { date: "2024-06-22", views: 317, shares: 270 },
  { date: "2024-06-23", views: 480, shares: 530 },
  { date: "2024-06-24", views: 132, shares: 180 },
  { date: "2024-06-25", views: 141, shares: 190 },
  { date: "2024-06-26", views: 434, shares: 380 },
  { date: "2024-06-27", views: 448, shares: 490 },
  { date: "2024-06-28", views: 149, shares: 200 },
  { date: "2024-06-29", views: 103, shares: 160 },
  { date: "2024-06-30", views: 446, shares: 400 },
]

const chartConfig = {
  engagement: {
    label: "Engagement",
  },
  views: {
    label: "Views",
    color: "var(--primary)",
  },
  shares: {
    label: "Shares",
    color: "var(--primary)",
  },
} satisfies ChartConfig

export function ChartAreaInteractive() {
  const isMobile = useIsMobile()
  const [timeRange, setTimeRange] = React.useState("90d")

  React.useEffect(() => {
    if (isMobile) {
      setTimeRange("7d")
    }
  }, [isMobile])

  const filteredData = chartData.filter((item) => {
    const date = new Date(item.date)
    const referenceDate = new Date("2024-06-30")
    let daysToSubtract = 90
    if (timeRange === "30d") {
      daysToSubtract = 30
    } else if (timeRange === "7d") {
      daysToSubtract = 7
    }
    const startDate = new Date(referenceDate)
    startDate.setDate(startDate.getDate() - daysToSubtract)
    return date >= startDate
  })

  return (
    <Card className="@container/card">
      <CardHeader>
        <CardTitle>Spiking Post Velocity</CardTitle>
        <CardDescription>
          <span className="hidden @[540px]/card:block">
            Engagement growth (P-89912)
          </span>
          <span className="@[540px]/card:hidden">Post P-89912</span>
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
          className="aspect-auto h-[250px] w-full"
        >
          <AreaChart data={filteredData}>
            <defs>
              <linearGradient id="fillViews" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="var(--color-views)"
                  stopOpacity={1.0}
                />
                <stop
                  offset="95%"
                  stopColor="var(--color-views)"
                  stopOpacity={0.1}
                />
              </linearGradient>
              <linearGradient id="fillShares" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="var(--color-shares)"
                  stopOpacity={0.8}
                />
                <stop
                  offset="95%"
                  stopColor="var(--color-shares)"
                  stopOpacity={0.1}
                />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} />
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
              dataKey="shares"
              type="natural"
              fill="url(#fillShares)"
              stroke="var(--color-shares)"
              stackId="a"
            />
            <Area
              dataKey="views"
              type="natural"
              fill="url(#fillViews)"
              stroke="var(--color-views)"
              stackId="a"
            />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
