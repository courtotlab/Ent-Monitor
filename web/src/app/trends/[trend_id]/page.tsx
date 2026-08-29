"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { PageShell } from "@/components/layout/page-shell"
import { fetchTrendDetails, type TrendDetails, type PostData } from "@/lib/api"
import { useApi } from "@/hooks/use-api"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from "@/components/ui/card"
import { ExternalLinkIcon, ShieldCheckIcon, ActivityIcon } from "lucide-react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table"

import { formatDate, formatShortDate, formatTrendName, parseUtcDate } from "@/lib/utils"
import { RiskBadge } from "@/components/shared/risk-badge"
import { LifecycleBadge } from "@/components/shared/lifecycle-badge"
import { SortableHeader } from "@/components/shared/sortable-header"
import { TimeRangeSelect } from "@/components/shared/time-range-select"
import { SidebarSection, BorderedTable } from "@/components/shared/sidebar-section"
import { filterByTimeRange, formatChartDate, AreaGradient, type TimeRange } from "@/lib/chart-helpers"

const chartConfig = {
  count: { label: "Posts", color: "#22c55e" },
} satisfies ChartConfig

const postColumns: ColumnDef<PostData>[] = [
  {
    accessorKey: "collected_at",
    header: ({ column }) => <SortableHeader column={column} label="Date" />,
    cell: ({ row }) => (
      <div className="whitespace-nowrap text-muted-foreground tabular-nums px-2">
        {formatDate(row.original.posted_at || row.original.collected_at)}
      </div>
    ),
    sortingFn: (a, b) => {
      const aDate = parseUtcDate(a.original.posted_at || a.original.collected_at)
      const bDate = parseUtcDate(b.original.posted_at || b.original.collected_at)
      return (aDate?.getTime() ?? 0) - (bDate?.getTime() ?? 0)
    },
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
    accessorKey: "caption_text",
    header: "Snippet",
    cell: ({ row }) => {
      const text = row.original.caption_text
      const url = row.original.url
      const content = text ? (
        text.length > 75 ? text.substring(0, 75) + "..." : text
      ) : (
        <span className="italic text-muted-foreground">No text</span>
      )
      return (
        <div className="text-sm max-w-[350px] whitespace-normal break-words" title={text || ""}>
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline hover:text-primary/80 transition-colors"
            >
              <span>{content}</span>
              <ExternalLinkIcon className="size-3.5 shrink-0 opacity-50 mb-[-2px]" />
            </a>
          ) : (
            content
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
  const params = useParams<{ trend_id: string }>()
  const trendId = params.trend_id ?? ""
  const { data, loading, error } = useApi<TrendDetails>(
    () => fetchTrendDetails(trendId),
    [trendId],
  )
  const [sorting, setSorting] = React.useState<SortingState>([])
  const [timeRange, setTimeRange] = React.useState<TimeRange>("30d")

  const filteredChartData = React.useMemo(
    () => filterByTimeRange(data?.chart_data ?? [], timeRange),
    [data?.chart_data, timeRange],
  )

  const table = useReactTable({
    data: data?.posts ?? [],
    columns: postColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (row) => row.post_id,
  })

  if (loading) {
    return (
      <PageShell>
        <div className="flex flex-1 items-center justify-center">
          <p className="text-muted-foreground text-sm">Loading details...</p>
        </div>
      </PageShell>
    )
  }

  if (error || !data) {
    return (
      <PageShell>
        <div className="flex flex-1 items-center justify-center">
          <p className="text-destructive text-sm font-medium">Failed to load trend details.</p>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell contentClassName="flex flex-1 flex-col mx-auto w-full max-w-[1600px] p-6 lg:p-10">
      <div className="flex flex-col xl:flex-row gap-8 w-full">
        <div className="flex-1 flex flex-col gap-8 min-w-0">
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-4 text-muted-foreground text-sm font-medium">
              <Link href="/trends" className="hover:text-foreground transition-colors">Trends</Link>
              <span>/</span>
              <span className="text-foreground">{data.trend.trend_name || formatTrendName(trendId)}</span>
            </div>

            <div className="flex flex-col gap-2">
              <h1 className="text-3xl font-bold tracking-tight">{data.trend.trend_name || formatTrendName(trendId)}</h1>
              <p className="text-muted-foreground text-sm leading-relaxed mt-2">
                {data.trend.abstract || "No description available"}
              </p>
            </div>

            {data.trend.slang_terms && data.trend.slang_terms.length > 0 && (
              <div className="flex flex-col gap-2 mt-1">
                <div className="flex items-baseline gap-2">
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Slang & Hashtags</h2>
                  <span className="text-xs text-muted-foreground/70 italic">(LLM generated · may include invented terms, not verified to exist on platforms)</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {data.trend.slang_terms.map((term, i) => (
                    <Badge key={i} variant="secondary" className="font-normal rounded-full">
                      {term}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 min-[500px]:grid-cols-2 lg:grid-cols-4 gap-4 *:data-[slot=card]:bg-linear-to-t *:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card *:data-[slot=card]:shadow-xs dark:*:data-[slot=card]:bg-card">
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
                <TimeRangeSelect value={timeRange} onChange={setTimeRange} />
              </CardAction>
            </CardHeader>
            <CardContent className="px-2 pt-2 sm:px-6 sm:pt-4">
              <ChartContainer config={chartConfig} className="aspect-auto h-[200px] sm:h-[300px] w-full">
                <AreaChart data={filteredChartData}>
                  <defs>
                    <AreaGradient id="fillCount" colorVar="count" />
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
                  <Area dataKey="count" type="monotone" fill="url(#fillCount)" stroke="var(--color-count)" strokeWidth={2} />
                </AreaChart>
              </ChartContainer>
            </CardContent>
          </Card>

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
                          {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
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

        <aside className="w-full xl:w-[400px] shrink-0 flex flex-col gap-6">
          <div className="sticky top-0 pt-0 flex flex-col gap-6">
            <SidebarSection title="Evidence Links" description="Direct sources found against this trend.">
              <BorderedTable>
                <TableHeader className="sticky top-0 z-10 bg-muted">
                  <TableRow>
                    <TableHead className="px-4 w-[100px]">Source</TableHead>
                    <TableHead className="px-4">Link</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.trend.evidence && data.trend.evidence.length > 0 ? (
                    data.trend.evidence.map((ev, i) => {
                      const titleText = ev.title || "External Source"
                      const words = titleText.split(" ")
                      const truncatedTitle = words.length > 10 ? words.slice(0, 10).join(" ") + "..." : titleText
                      return (
                        <TableRow key={i}>
                          <TableCell className="px-4 py-3 align-top">
                            <Badge variant="outline" className="text-[10px] uppercase tracking-wider shrink-0 mt-0.5">
                              {ev.source}
                            </Badge>
                          </TableCell>
                          <TableCell className="px-4 py-3 align-top">
                            <a href={ev.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline hover:text-primary/80 transition-colors" title={ev.title}>
                              <span>{truncatedTitle}</span>
                              <ExternalLinkIcon className="size-3.5 shrink-0 opacity-50 mb-[-2px]" />
                            </a>
                          </TableCell>
                        </TableRow>
                      )
                    })
                  ) : (
                    <TableRow>
                      <TableCell colSpan={2} className="h-32 text-center text-muted-foreground text-sm">
                        No external URLs found.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </BorderedTable>
            </SidebarSection>

            {data.trend.harm_mechanism && (
              <SidebarSection title="Harm Mechanism" description="Clinical pathway identified by the agent.">
                <div className="rounded-lg border bg-destructive/5 border-destructive/15 px-4 py-3">
                  <p className="text-sm leading-relaxed text-foreground/90">{data.trend.harm_mechanism}</p>
                </div>
              </SidebarSection>
            )}

            {data.trend.should_monitor && (
              <SidebarSection
                title="Velocity Monitor"
                description="Real-time growth tracking."
                icon={ActivityIcon}
                titleClassName="text-amber-600 dark:text-amber-500"
              >
                <div className="overflow-hidden rounded-lg border border-amber-500/20 bg-amber-500/5">
                  <Table>
                    <TableBody>
                      <TableRow>
                        <TableCell className="px-4 py-3 text-amber-900/70 dark:text-amber-500/70 font-medium border-b border-amber-500/10">Status</TableCell>
                        <TableCell className="px-4 py-3 text-right tabular-nums border-b border-amber-500/10">
                          <Badge variant="outline" className="bg-amber-500/10 text-amber-600 dark:text-amber-400 border-0">Active</Badge>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell className="px-4 py-3 text-amber-900/70 dark:text-amber-500/70 font-medium">Growth Rate</TableCell>
                        <TableCell className="px-4 py-3 text-right tabular-nums text-amber-700 dark:text-amber-400 font-medium">
                          {data.trend.velocity_growth_rate ? `+${data.trend.velocity_growth_rate.toFixed(2)} posts/hr` : "Calculating..."}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </div>
              </SidebarSection>
            )}

            {data.trend.lifecycle_history && data.trend.lifecycle_history.length > 0 && (
              <SidebarSection title="Lifecycle History" description="Status changes over time.">
                <Table wrapperClassName="[&[data-slot=table-container]]:overflow-x-hidden [&[data-slot=table-container]]:overflow-y-auto [&[data-slot=table-container]]:max-h-56 [&[data-slot=table-container]]:rounded-lg [&[data-slot=table-container]]:border custom-scrollbar">
                  <TableHeader className="sticky top-0 z-10 bg-muted">
                    <TableRow>
                      <TableHead className="px-4">Date</TableHead>
                      <TableHead className="px-4">Status</TableHead>
                      <TableHead className="px-4 text-right">Posts</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[...data.trend.lifecycle_history].reverse().map((entry, i) => (
                      <TableRow key={i}>
                        <TableCell className="px-4 py-2 tabular-nums text-muted-foreground text-xs whitespace-nowrap">
                          {formatShortDate(entry.date, { withYear: true })}
                        </TableCell>
                        <TableCell className="px-4 py-2">
                          <LifecycleBadge status={entry.status} />
                        </TableCell>
                        <TableCell className="px-4 py-2 text-right tabular-nums text-sm">
                          {entry.post_count.toLocaleString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </SidebarSection>
            )}

            <SidebarSection title="Timeline" description="Activity duration.">
              <BorderedTable>
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
              </BorderedTable>
            </SidebarSection>
          </div>
        </aside>
      </div>
    </PageShell>
  )
}
