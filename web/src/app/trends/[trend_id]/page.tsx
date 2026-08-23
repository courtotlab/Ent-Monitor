"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { AppNavbar } from "@/components/layout/app-navbar"
import { fetchTrendDetails, type TrendDetails, type PostData } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction, CardFooter } from "@/components/ui/card"
import { AlertTriangleIcon, AlertCircleIcon, ExternalLinkIcon, ShieldCheckIcon, ActivityIcon, ChevronUpIcon, ChevronDownIcon, ChevronsUpDownIcon } from "lucide-react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table"

// Helpers
type RiskLevel = "HIGH" | "MODERATE" | "LOW"

function formatDate(iso: string | null) {
  if (!iso) return "-"
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })
}

function formatTrendName(trendId: string) {
  return trendId
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function RiskBadge({ label, score }: { label: RiskLevel; score: number }) {
  const pct = Math.round(score * 100)
  if (label === "HIGH" || score >= 0.7) return (
    <Badge variant="destructive" className="tabular-nums bg-destructive/10 text-destructive border-0 hover:bg-destructive/20">
      <AlertTriangleIcon className="mr-1 size-3" />{pct}%
    </Badge>
  )
  if (label === "MODERATE" || score >= 0.4) return (
    <Badge className="tabular-nums bg-amber-500/10 text-amber-600 border-0 dark:text-amber-400 hover:bg-amber-500/20">
      <AlertCircleIcon className="mr-1 size-3" />{pct}%
    </Badge>
  )
  return <Badge variant="outline" className="tabular-nums text-muted-foreground border-0 bg-muted/50">{pct}%</Badge>
}

const lifecycleStyles: Record<string, string> = {
  Emergence: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-0",
  Growth: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-0",
  Resurfacing: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-0",
  Declining: "bg-muted text-muted-foreground border-0",
  Latent: "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-0",
  "Isolated incident": "bg-muted text-muted-foreground border-0",
}

function LifecycleBadge({ status }: { status: string }) {
  return <Badge className={lifecycleStyles[status] ?? "border-0"}>{status}</Badge>
}

const chartConfig = {
  count: {
    label: "Posts",
    color: "#22c55e",
  },
} satisfies ChartConfig

// Data Table components for Posts Analyzed
function SortableHeader({
  column,
  label,
}: {
  column: { toggleSorting: (asc: boolean) => void; getIsSorted: () => false | "asc" | "desc" }
  label: string
}) {
  const sorted = column.getIsSorted()
  return (
    <button
      className="flex items-center gap-1 text-left font-medium hover:text-foreground transition-colors"
      onClick={() => column.toggleSorting(sorted === "asc")}
    >
      {label}
      {sorted === "asc" ? (
        <ChevronUpIcon className="size-3.5" />
      ) : sorted === "desc" ? (
        <ChevronDownIcon className="size-3.5" />
      ) : (
        <ChevronsUpDownIcon className="size-3.5 opacity-40" />
      )}
    </button>
  )
}

const postColumns: ColumnDef<PostData>[] = [
  {
    accessorKey: "collected_at",
    header: ({ column }) => <SortableHeader column={column} label="Date" />,
    cell: ({ row }) => (
      <span className="text-muted-foreground text-sm whitespace-nowrap">
        {formatDate(row.original.collected_at)}
      </span>
    ),
    sortingFn: (a, b) => {
      const aDate = a.original.collected_at ? new Date(a.original.collected_at).getTime() : 0
      const bDate = b.original.collected_at ? new Date(b.original.collected_at).getTime() : 0
      return aDate - bDate
    }
  },
  {
    accessorKey: "platform",
    header: ({ column }) => <SortableHeader column={column} label="Platform" />,
    cell: ({ row }) => (
      <Badge variant="outline" className="text-xs capitalize">
        {row.original.platform}
      </Badge>
    ),
  },
  {
    accessorKey: "creator_id",
    header: ({ column }) => <SortableHeader column={column} label="Creator ID" />,
    cell: ({ row }) => (
      <span className="font-medium min-w-[120px] inline-block">
        {row.original.creator_id || <span className="text-muted-foreground font-normal italic">Anonymous</span>}
      </span>
    ),
  },
  {
    accessorKey: "caption_text",
    header: "Snippet",
    cell: ({ row }) => {
      const text = row.original.caption_text
      return (
        <div className="text-sm truncate max-w-[250px]" title={text || ""}>
          {text ? (
            text.length > 50 ? text.substring(0, 50) + "..." : text
          ) : (
            <span className="italic text-muted-foreground">No text</span>
          )}
        </div>
      )
    },
  },
  {
    accessorKey: "likes",
    header: ({ column }) => (
      <div className="flex justify-end"><SortableHeader column={column} label="Likes" /></div>
    ),
    cell: ({ row }) => <div className="text-right tabular-nums">{row.original.likes.toLocaleString()}</div>,
  },
  {
    accessorKey: "views",
    header: ({ column }) => (
      <div className="flex justify-end"><SortableHeader column={column} label="Views" /></div>
    ),
    cell: ({ row }) => <div className="text-right tabular-nums">{row.original.views.toLocaleString()}</div>,
  },
]


export default function TrendDetailsPage() {
  const params = useParams()
  const trendId = params.trend_id as string
  const [data, setData] = React.useState<TrendDetails | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState(false)
  const [sorting, setSorting] = React.useState<SortingState>([])

  React.useEffect(() => {
    fetchTrendDetails(trendId)
      .then(setData)
      .catch((err) => {
        console.error(err)
        setError(true)
      })
      .finally(() => setLoading(false))
  }, [trendId])

  const [timeRange, setTimeRange] = React.useState("30d")

  // Filter chart data for the selected time range and fill missing dates
  const filteredChartData = React.useMemo(() => {
    if (!data?.chart_data) return []
    
    let endDateStr = new Date().toISOString().split('T')[0]
    if (data.chart_data.length > 0) {
      endDateStr = data.chart_data[data.chart_data.length - 1].date.split('T')[0]
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
    
    const dataMap = new Map(data.chart_data.map(item => [item.date.split('T')[0], item]))
    
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
          count: 0
        })
      }
    }
    
    return result
  }, [data?.chart_data, timeRange])

  const table = useReactTable({
    data: data?.posts || [],
    columns: postColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (row) => row.post_id,
  })

  return (
    <div className="flex min-h-svh flex-col bg-sidebar">
      <AppNavbar />

      <div className="flex flex-1 gap-0 p-2 pt-0 overflow-hidden">
        <main className="flex flex-1 flex-col overflow-y-auto rounded-2xl shadow-sm bg-background min-w-0" id="scroll-container">
          <div className="flex flex-1 flex-col mx-auto w-full max-w-[1600px] p-6 lg:p-10">
            {loading ? (
              <div className="flex flex-1 items-center justify-center">
                <p className="text-muted-foreground text-sm">Loading details...</p>
              </div>
            ) : error || !data ? (
              <div className="flex flex-1 items-center justify-center">
                <p className="text-destructive text-sm font-medium">Failed to load trend details.</p>
              </div>
            ) : (
              <div className="flex flex-col xl:flex-row gap-8 w-full">
                
                {/* Main Content Area (Left/Center) */}
                <div className="flex-1 flex flex-col gap-8 min-w-0">
                  
                  {/* Top Header Section */}
                  <div className="flex flex-col gap-4">
                    <div className="flex items-center gap-4 text-muted-foreground text-sm font-medium">
                      <Link href="/trends" className="hover:text-foreground transition-colors">Trends</Link>
                      <span>/</span>
                      <span className="text-foreground">{data.trend.trend_name || formatTrendName(trendId)}</span>
                    </div>

                    <div className="flex flex-col gap-2">
                      <h1 className="text-3xl font-bold tracking-tight">{data.trend.trend_name || formatTrendName(trendId)}</h1>
                      <p className="text-muted-foreground text-sm max-w-3xl leading-relaxed mt-2">
                        {data.trend.abstract || "No description available"}
                      </p>
                    </div>
                  </div>

                  {/* Section Cards (Mini Scale, like dashboard stats) */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 *:data-[slot=card]:bg-linear-to-t *:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card *:data-[slot=card]:shadow-xs dark:*:data-[slot=card]:bg-card">
                    
                    <Card className="@container/card">
                      <CardHeader>
                        <CardDescription>Risk Score</CardDescription>
                        <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                          {data.trend.risk_score.toFixed(2)}
                        </CardTitle>
                        <CardAction>
                          <RiskBadge label={data.trend.label} score={data.trend.risk_score} />
                        </CardAction>
                      </CardHeader>
                    </Card>

                    <Card className="@container/card">
                      <CardHeader>
                        <CardDescription>Total Posts</CardDescription>
                        <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                          {data.trend.post_count.toLocaleString()}
                        </CardTitle>
                        <CardAction>
                          <Badge variant="outline" className="bg-purple-500/10 text-purple-600 hover:bg-purple-500/20 border-0 dark:text-purple-400">
                            <ActivityIcon className="mr-1 h-3 w-3" />
                            Volume
                          </Badge>
                        </CardAction>
                      </CardHeader>
                    </Card>

                    <Card className="@container/card">
                      <CardHeader>
                        <CardDescription>Lifecycle</CardDescription>
                        <CardTitle className="text-lg font-semibold truncate pt-1 pb-1 @[250px]/card:text-xl">
                          {data.trend.lifecycle_status}
                        </CardTitle>
                        <CardAction>
                          <LifecycleBadge status={data.trend.lifecycle_status} />
                        </CardAction>
                      </CardHeader>
                    </Card>

                    <Card className="@container/card">
                      <CardHeader>
                        <CardDescription>Verification</CardDescription>
                        <CardTitle className="text-lg font-semibold truncate pt-1 pb-1 @[250px]/card:text-xl">
                          {data.trend.verification_status}
                        </CardTitle>
                        <CardAction>
                           <Badge variant="outline" className="bg-green-500/10 text-green-600 hover:bg-green-500/20 border-0 dark:text-green-400">
                             <ShieldCheckIcon className="mr-1 h-3 w-3" />
                             Status
                           </Badge>
                        </CardAction>
                      </CardHeader>
                    </Card>

                  </div>

                  {/* Volume Chart (Dashboard Style) */}
                  <Card className="@container/card">
                    <CardHeader>
                      <CardTitle>Post Volume</CardTitle>
                      <CardDescription>
                        <span className="hidden @[540px]/card:block">
                          Daily tracked post volume across all platforms
                        </span>
                        <span className="@[540px]/card:hidden">Post Volume</span>
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
                    <CardContent className="px-2 pt-2 sm:px-6 sm:pt-4">
                      <ChartContainer config={chartConfig} className="aspect-auto h-[300px] w-full">
                        <AreaChart data={filteredChartData}>
                          <defs>
                            <linearGradient id="fillCount" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="var(--color-count)" stopOpacity={0.8} />
                              <stop offset="95%" stopColor="var(--color-count)" stopOpacity={0.1} />
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
                              const date = new Date(`${value}T12:00:00Z`)
                              return date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })
                            }}
                          />
                          <ChartTooltip
                            cursor={false}
                            isAnimationActive={false}
                            content={
                              <ChartTooltipContent
                                labelFormatter={(value) => {
                                  if (!value) return ""
                                  return new Date(`${value}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })
                                }}
                                indicator="dot"
                              />
                            }
                          />
                          <Area
                            dataKey="count"
                            type="monotone"
                            fill="url(#fillCount)"
                            stroke="var(--color-count)"
                            strokeWidth={2}
                          />
                        </AreaChart>
                      </ChartContainer>
                    </CardContent>
                  </Card>

                  {/* Historical Posts Data Table */}
                  <div className="flex flex-col gap-4">
                    <div className="flex items-center justify-between px-2">
                      <h2 className="text-lg font-semibold">Posts Analyzed</h2>
                      <p className="text-sm text-muted-foreground">{data.posts.length} Total</p>
                    </div>
                    
                    <div className="overflow-hidden rounded-lg border">
                      <Table>
                        <TableHeader className="sticky top-0 z-10 bg-muted">
                          {table.getHeaderGroups().map((headerGroup) => (
                            <TableRow key={headerGroup.id}>
                              {headerGroup.headers.map((header) => (
                                <TableHead key={header.id} className="px-4">
                                  {header.isPlaceholder
                                    ? null
                                    : flexRender(header.column.columnDef.header, header.getContext())}
                                </TableHead>
                              ))}
                            </TableRow>
                          ))}
                        </TableHeader>
                        <TableBody>
                          {table.getRowModel().rows.length ? (
                            table.getRowModel().rows.map((row) => (
                              <TableRow key={row.id}>
                                {row.getVisibleCells().map((cell) => (
                                  <TableCell key={cell.id} className="px-4 py-3">
                                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                  </TableCell>
                                ))}
                              </TableRow>
                            ))
                          ) : (
                            <TableRow>
                              <TableCell colSpan={postColumns.length} className="h-32 text-center text-muted-foreground">
                                No posts found for this trend.
                              </TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                  
                </div>

                {/* Right Sidebar (Evidence) */}
                <aside className="w-full xl:w-[400px] shrink-0 flex flex-col gap-6">
                  <div className="sticky top-0 pt-0 flex flex-col gap-6">
                    
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-col gap-1 px-1">
                        <h2 className="text-lg font-semibold">Evidence Links</h2>
                        <p className="text-sm text-muted-foreground">Direct sources found against this trend.</p>
                      </div>

                      <div className="overflow-hidden rounded-lg border">
                        <Table>
                          <TableHeader className="sticky top-0 z-10 bg-muted">
                            <TableRow>
                              <TableHead className="px-4 w-[100px]">Source</TableHead>
                              <TableHead className="px-4">Link</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {data.trend.evidence && data.trend.evidence.length > 0 ? (
                              data.trend.evidence.map((ev, i) => {
                                const titleText = ev.title || "External Source";
                                const words = titleText.split(" ");
                                const truncatedTitle = words.length > 10 ? words.slice(0, 10).join(" ") + "..." : titleText;
                                
                                return (
                                <TableRow key={i}>
                                  <TableCell className="px-4 py-3 align-top">
                                    <Badge variant="outline" className="text-[10px] uppercase tracking-wider shrink-0 mt-0.5">
                                      {ev.source}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="px-4 py-3 align-top">
                                    <a 
                                      href={ev.url} 
                                      target="_blank" 
                                      rel="noreferrer" 
                                      className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline hover:text-primary/80 transition-colors"
                                      title={ev.title}
                                    >
                                      <span>
                                        {truncatedTitle}
                                      </span>
                                      <ExternalLinkIcon className="size-3.5 shrink-0 opacity-50 mb-[-2px]" />
                                    </a>
                                  </TableCell>
                                </TableRow>
                                );
                              })
                            ) : (
                              <TableRow>
                                <TableCell colSpan={2} className="h-32 text-center text-muted-foreground text-sm">
                                  No external URLs found.
                                </TableCell>
                              </TableRow>
                            )}
                          </TableBody>
                        </Table>
                      </div>
                    </div>

                    <div className="flex flex-col gap-2">
                      <div className="flex flex-col gap-1 px-1">
                        <h2 className="text-lg font-semibold">Timeline</h2>
                        <p className="text-sm text-muted-foreground">Activity duration.</p>
                      </div>

                      <div className="overflow-hidden rounded-lg border">
                        <Table>
                          <TableBody>
                            <TableRow>
                              <TableCell className="px-4 py-3 text-muted-foreground font-medium border-b">First Detected</TableCell>
                              <TableCell className="px-4 py-3 text-right tabular-nums border-b">{formatDate(data.trend.first_detected_at)}</TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell className="px-4 py-3 text-muted-foreground font-medium">Last Seen</TableCell>
                              <TableCell className="px-4 py-3 text-right tabular-nums">{formatDate(data.trend.last_seen_at)}</TableCell>
                            </TableRow>
                          </TableBody>
                        </Table>
                      </div>
                    </div>

                  </div>
                </aside>

              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
