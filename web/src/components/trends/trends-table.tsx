"use client"

import * as React from "react"
import Link from "next/link"
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table"
import {
  SearchIcon,
  EyeIcon,
  AlertTriangleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ChevronsUpDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
  CalendarIcon,
  XIcon,
} from "lucide-react"
import { format } from "date-fns"
import { type DateRange } from "react-day-picker"

import { Calendar } from "@/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"


import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fetchAllTrends, type TrendData } from "@/lib/api"

// Helpers 

type RiskLevel = "HIGH" | "MODERATE" | "LOW"

function formatDate(iso: string | null) {
  if (!iso) return "-"
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

function formatTrendName(trendId: string) {
  return trendId
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function RiskBadge({ label, score }: { label: RiskLevel; score: number }) {
  if (label === "HIGH") return (
    <Badge variant="destructive" className="gap-1 tabular-nums">
      <AlertTriangleIcon className="size-3" />{score.toFixed(2)}
    </Badge>
  )
  if (label === "MODERATE") return (
    <Badge className="bg-amber-500/10 text-amber-600 border-0 gap-1 tabular-nums dark:text-amber-400">
      <AlertTriangleIcon className="size-3" />{score.toFixed(2)}
    </Badge>
  )
  return <Badge variant="outline" className="gap-1 tabular-nums text-muted-foreground">{score.toFixed(2)}</Badge>
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
  return (
    <Badge className={lifecycleStyles[status] ?? "border-0"}>
      {status}
    </Badge>
  )
}

const verificationStyles: Record<string, string> = {
  CONFIRMED: "bg-green-500/10 text-green-600 dark:text-green-400 border-0",
  PROVISIONAL: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-0",
  INSUFFICIENT_EVIDENCE: "bg-muted text-muted-foreground border-0",
}

function VerificationBadge({ status }: { status: string }) {
  return (
    <Badge className={verificationStyles[status] ?? "border-0"}>
      {status}
    </Badge>
  )
}

// Sortable header helper 

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
      {sorted === "asc" ? <ChevronUpIcon className="size-3.5" /> :
       sorted === "desc" ? <ChevronDownIcon className="size-3.5" /> :
       <ChevronsUpDownIcon className="size-3.5 opacity-40" />}
    </button>
  )
}

// Column definitions

const columns: ColumnDef<TrendData>[] = [
  {
    id: "trend_name",
    accessorFn: (row) => row.trend_name || formatTrendName(row.trend_id),
    header: ({ column }) => <SortableHeader column={column} label="Trend Name" />,
    cell: ({ getValue }) => (
      <div className="min-w-[160px]">
        <span className="font-medium">{getValue() as string}</span>
      </div>
    ),
    enableHiding: false,
  },
  {
    accessorKey: "first_detected_at",
    header: ({ column }) => <SortableHeader column={column} label="First Detected" />,
    cell: ({ row }) => <span className="text-muted-foreground">{formatDate(row.original.first_detected_at)}</span>,
    sortingFn: (a, b) => {
      const aTime = a.original.first_detected_at ? new Date(a.original.first_detected_at).getTime() : 0
      const bTime = b.original.first_detected_at ? new Date(b.original.first_detected_at).getTime() : 0
      return aTime - bTime
    },
  },
  {
    accessorKey: "last_seen_at",
    header: ({ column }) => <SortableHeader column={column} label="Last Seen" />,
    cell: ({ row }) => <span className="text-muted-foreground">{formatDate(row.original.last_seen_at)}</span>,
    sortingFn: (a, b) => {
      const aTime = a.original.last_seen_at ? new Date(a.original.last_seen_at).getTime() : 0
      const bTime = b.original.last_seen_at ? new Date(b.original.last_seen_at).getTime() : 0
      return aTime - bTime
    },
  },
  {
    accessorKey: "post_count",
    header: ({ column }) => <SortableHeader column={column} label="Posts" />,
    cell: ({ row }) => <span className="tabular-nums">{row.original.post_count.toLocaleString()}</span>,
  },
  {
    accessorKey: "risk_score",
    header: ({ column }) => <SortableHeader column={column} label="Risk Score" />,
    cell: ({ row }) => <RiskBadge label={row.original.label} score={row.original.risk_score} />,
  },
  {
    accessorKey: "lifecycle_status",
    header: "Lifecycle",
    cell: ({ row }) => <LifecycleBadge status={row.original.lifecycle_status} />,
  },
  {
    accessorKey: "verification_status",
    header: "Verification",
    cell: ({ row }) => <VerificationBadge status={row.original.verification_status} />,
  },
  {
    accessorKey: "platforms",
    header: "Platforms",
    cell: ({ row }) => (
      <div className="flex flex-wrap gap-1">
        {(row.original.platforms ?? []).map((p) => (
          <Badge key={p} variant="outline">{p}</Badge>
        ))}
      </div>
    ),
    enableSorting: false,
  },
  {
    id: "actions",
    header: "",
    cell: ({ row }) => (
      <Button 
        variant="outline" 
        size="sm" 
        className="h-7 gap-1.5 text-xs"
        render={<Link href={`/trends/${row.original.trend_id}`} />}
        nativeButton={false}
      >
        <EyeIcon className="size-3.5" />
        View Details
      </Button>
    ),
    enableSorting: false,
  },
]

// Main component 

export function TrendsTable() {
  const [allTrends, setAllTrends] = React.useState<TrendData[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState(false)

  const [search, setSearch] = React.useState("")
  const [riskFilter, setRiskFilter] = React.useState("all")
  const [statusFilter, setStatusFilter] = React.useState("all")
  const [platformFilter, setPlatformFilter] = React.useState("all")
  const [postsFilter, setPostsFilter] = React.useState("all")
  const [dateRange, setDateRange] = React.useState<DateRange | undefined>()
  const [dateFilterType, setDateFilterType] = React.useState<"first_detected_at" | "last_seen_at">("first_detected_at")
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: "first_detected_at", desc: true },
  ])

  // Fetch trends from the API
  React.useEffect(() => {
    fetchAllTrends()
      .then((trends) => {
        setAllTrends(trends)
        setLoading(false)
      })
      .catch((err) => {
        console.error("Failed to load trends:", err)
        setError(true)
        setLoading(false)
      })
  }, [])

  // Derive unique platforms from data
  const allPlatforms = React.useMemo(() => {
    const set = new Set<string>()
    allTrends.forEach((t) => (t.platforms ?? []).forEach((p) => set.add(p)))
    return Array.from(set).sort()
  }, [allTrends])

  // Apply search + filter before table sees data
  const filtered = React.useMemo(() => {
    const q = search.toLowerCase()
    return allTrends.filter((t) => {
      const name = (t.trend_name || formatTrendName(t.trend_id)).toLowerCase()
      const matchSearch = !q || name.includes(q) ||
        (t.platforms ?? []).some((p) => p.toLowerCase().includes(q))

      const matchRisk = riskFilter === "all" || t.label === riskFilter
      const matchStatus = statusFilter === "all" || t.lifecycle_status === statusFilter
      const matchPlatform =
        platformFilter === "all" ||
        (t.platforms ?? []).some((p) => p === platformFilter)
      const matchPosts =
        postsFilter === "all" ||
        (postsFilter === "<100" && t.post_count < 100) ||
        (postsFilter === "100-500" && t.post_count >= 100 && t.post_count <= 500) ||
        (postsFilter === ">500" && t.post_count > 500)
        
      let matchDate = true
      if (dateRange?.from) {
        const dStr = dateFilterType === "first_detected_at" ? t.first_detected_at : t.last_seen_at
        if (dStr) {
          const d = new Date(dStr)
          const from = new Date(dateRange.from)
          from.setHours(0, 0, 0, 0)
          if (d < from) matchDate = false
          
          if (dateRange.to) {
            const to = new Date(dateRange.to)
            to.setHours(23, 59, 59, 999)
            if (d > to) matchDate = false
          }
        } else {
          matchDate = false
        }
      }

      return matchSearch && matchRisk && matchStatus && matchPlatform && matchPosts && matchDate
    })
  }, [allTrends, search, riskFilter, statusFilter, platformFilter, postsFilter, dateRange, dateFilterType])

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 10 } },
    getRowId: (row) => row.trend_id,
  })

  const isFiltered = search.length > 0 || riskFilter !== "all" || statusFilter !== "all" || platformFilter !== "all" || postsFilter !== "all" || dateRange !== undefined

  return (
    <div className="flex flex-col gap-4">
      {/* Row 1: Search bar (full width) */}
      <div className="relative flex items-center h-8 w-full rounded-2xl border border-transparent bg-input/50 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30 transition-[color,box-shadow] duration-200">
        <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
        <input
          id="trends-search"
          type="search"
          placeholder="Search trends, platforms…"
          className="flex-1 bg-transparent pl-8 pr-2.5 py-1 text-sm outline-none min-w-0 text-foreground placeholder:text-muted-foreground"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Row 2: Filters with labels */}
      <div className="flex items-center gap-4 flex-wrap">
        {/* Risk level */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Risk</span>
          <Select value={riskFilter} onValueChange={(val) => setRiskFilter(val || "all")}>
            <SelectTrigger id="risk-filter" className="w-36 h-8 text-sm">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">All levels</SelectItem>
                <SelectItem value="HIGH">High Risk</SelectItem>
                <SelectItem value="MODERATE">Moderate Risk</SelectItem>
                <SelectItem value="LOW">Low Risk</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        {/* Lifecycle status */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Lifecycle</span>
          <Select value={statusFilter} onValueChange={(val) => setStatusFilter(val || "all")}>
            <SelectTrigger id="status-filter" className="w-36 h-8 text-sm">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="Emergence">Emergence</SelectItem>
                <SelectItem value="Growth">Growth</SelectItem>
                <SelectItem value="Resurfacing">Resurfacing</SelectItem>
                <SelectItem value="Declining">Declining</SelectItem>
                <SelectItem value="Latent">Latent</SelectItem>
                <SelectItem value="Isolated incident">Isolated incident</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        {/* Platform */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Platform</span>
          <Select value={platformFilter} onValueChange={(val) => setPlatformFilter(val || "all")}>
            <SelectTrigger id="platform-filter" className="w-36 h-8 text-sm">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">All platforms</SelectItem>
                {allPlatforms.map((p) => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        {/* Posts */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Posts</span>
          <Select value={postsFilter} onValueChange={(val) => setPostsFilter(val || "all")}>
            <SelectTrigger id="posts-filter" className="w-32 h-8 text-sm">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">All volume</SelectItem>
                <SelectItem value="<100">Under 100</SelectItem>
                <SelectItem value="100-500">100 - 500</SelectItem>
                <SelectItem value=">500">Over 500</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        {/* Date Range */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Date</span>
          <Popover>
            <PopoverTrigger
              render={
                <Button
                  variant="ghost"
                  id="date-picker-range"
                  className={`justify-between text-left font-normal h-8 px-3 text-sm rounded-2xl border border-transparent bg-input/50 hover:bg-input/80 hover:text-accent-foreground ${
                    dateRange?.from ? "w-[220px]" : "w-[165px]"
                  }`}
                >
                  <div className="flex items-center truncate">
                    <CalendarIcon className="mr-2 size-4 shrink-0" />
                    {dateRange?.from ? (
                      <span className="truncate">
                        <span className="text-muted-foreground mr-1">
                          {dateFilterType === "first_detected_at" ? "First:" : "Last:"}
                        </span>
                        {dateRange.to ? (
                          <>
                            {format(dateRange.from, "LLL dd")} - {format(dateRange.to, "LLL dd")}
                          </>
                        ) : (
                          format(dateRange.from, "LLL dd, y")
                        )}
                      </span>
                    ) : (
                      <span className="truncate">Select range...</span>
                    )}
                  </div>
                </Button>
              }
            />
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="range"
                defaultMonth={dateRange?.from}
                selected={dateRange}
                onSelect={setDateRange}
                numberOfMonths={2}
              />
              <div className="p-3 border-t flex items-center justify-between bg-muted/20">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-muted-foreground">Apply to:</span>
                  <div className="flex bg-muted/60 p-1 rounded-md">
                    <button 
                      className={`h-7 px-3 text-xs font-medium rounded-sm transition-colors ${
                        dateFilterType === "first_detected_at" 
                          ? "bg-background text-foreground shadow-sm" 
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                      onClick={() => setDateFilterType("first_detected_at")}
                    >
                      First Detected
                    </button>
                    <button 
                      className={`h-7 px-3 text-xs font-medium rounded-sm transition-colors ${
                        dateFilterType === "last_seen_at" 
                          ? "bg-background text-foreground shadow-sm" 
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                      onClick={() => setDateFilterType("last_seen_at")}
                    >
                      Last Seen
                    </button>
                  </div>
                </div>
                {dateRange?.from && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 px-3 text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => setDateRange(undefined)}
                  >
                    Clear
                  </Button>
                )}
              </div>
            </PopoverContent>
          </Popover>
        </div>

        {isFiltered && (
          <Button
            variant="ghost"
            onClick={() => {
              setSearch("")
              setRiskFilter("all")
              setStatusFilter("all")
              setPlatformFilter("all")
              setPostsFilter("all")
              setDateRange(undefined)
              setDateFilterType("first_detected_at")
            }}
            className="h-8 px-2 lg:px-3 text-sm text-muted-foreground hover:text-foreground"
          >
            Clear filters
            <XIcon className="ml-2 size-4" />
          </Button>
        )}
      </div>

      {/* Table */}
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
            {loading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <TableRow key={`skeleton-${i}`}>
                  {columns.map((_, ci) => (
                    <TableCell key={ci} className="px-4 py-3">
                      <span className="inline-block h-4 w-20 animate-pulse rounded bg-muted" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : error ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-32 text-center">
                  <div className="flex flex-col items-center gap-1 text-destructive">
                    <p className="font-medium">Failed to load trends</p>
                    <p className="text-xs">Is the API server running?</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows.length ? (
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
                <TableCell colSpan={columns.length} className="h-32 text-center text-muted-foreground">
                  <div className="flex flex-col items-center gap-1">
                    <SearchIcon className="size-7 opacity-30" />
                    <p className="font-medium">No trends found</p>
                    <p className="text-xs">Try adjusting your search or filters</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between px-1">
        <div className="flex-1 text-sm text-muted-foreground">
          {loading
            ? "Loading…"
            : filtered.length === allTrends.length
            ? `${allTrends.length} trends`
            : `${filtered.length} of ${allTrends.length} trends`}
        </div>
        <div className="flex items-center gap-6">
          <div className="hidden items-center gap-2 lg:flex">
            <Label htmlFor="rows-per-page" className="text-sm font-medium">Rows per page</Label>
            <Select
              value={`${table.getState().pagination.pageSize}`}
              onValueChange={(v) => table.setPageSize(Number(v))}
            >
              <SelectTrigger size="sm" className="w-16" id="rows-per-page">
                <SelectValue />
              </SelectTrigger>
              <SelectContent side="top">
                <SelectGroup>
                  {[10, 20, 50, 100].map((s) => (
                    <SelectItem key={s} value={`${s}`}>{s}</SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="text-sm font-medium">
            Page {table.getState().pagination.pageIndex + 1} of {Math.max(table.getPageCount(), 1)}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" className="hidden size-8 lg:flex" size="icon"
              onClick={() => table.setPageIndex(0)} disabled={!table.getCanPreviousPage()}>
              <ChevronsLeftIcon />
            </Button>
            <Button variant="outline" className="size-8" size="icon"
              onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
              <ChevronLeftIcon />
            </Button>
            <Button variant="outline" className="size-8" size="icon"
              onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
              <ChevronRightIcon />
            </Button>
            <Button variant="outline" className="hidden size-8 lg:flex" size="icon"
              onClick={() => table.setPageIndex(table.getPageCount() - 1)} disabled={!table.getCanNextPage()}>
              <ChevronsRightIcon />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
