"use client"

import * as React from "react"
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
} from "lucide-react"


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

// ─── Types & data ─────────────────────────────────────────────────────────────

type RiskLevel = "harmful" | "concerning" | "low"
type TrendStatus = "peak" | "growing" | "declining" | "monitoring" | "resurgence"

interface Trend {
  id: string
  name: string
  firstDetected: string
  posts: number
  riskScore: number
  riskLevel: RiskLevel
  status: TrendStatus
  platforms: string[]
}

const ALL_TRENDS: Trend[] = [
  { id: "t1",  name: "Garlic ear remedy",                    firstDetected: "2025-06-14", posts: 847, riskScore: 0.92, riskLevel: "harmful",    status: "peak",       platforms: ["TikTok","Instagram","Reddit"] },
  { id: "t2",  name: "Bobby pin tonsil stone removal",       firstDetected: "2025-06-28", posts: 203, riskScore: 0.88, riskLevel: "harmful",    status: "growing",    platforms: ["TikTok"] },
  { id: "t3",  name: "Ear candle wax removal",               firstDetected: "2025-03-01", posts:  91, riskScore: 0.71, riskLevel: "concerning", status: "resurgence",  platforms: ["TikTok","Instagram"] },
  { id: "t4",  name: "Orbeez in ear challenge",              firstDetected: "2025-07-20", posts: 312, riskScore: 0.85, riskLevel: "harmful",    status: "growing",    platforms: ["TikTok"] },
  { id: "t5",  name: "Cotton swab ear drum percussion",      firstDetected: "2025-07-25", posts:  58, riskScore: 0.67, riskLevel: "concerning", status: "monitoring", platforms: ["YouTube","Reddit"] },
  { id: "t6",  name: "Nasal insertion challenge",            firstDetected: "2025-05-10", posts:  38, riskScore: 0.79, riskLevel: "concerning", status: "declining",  platforms: ["TikTok","Instagram"] },
  { id: "t7",  name: "DIY ear syringe irrigation",           firstDetected: "2025-04-22", posts: 145, riskScore: 0.45, riskLevel: "low",        status: "monitoring", platforms: ["YouTube"] },
  { id: "t8",  name: "Hydrogen peroxide ear drops",          firstDetected: "2025-02-14", posts: 526, riskScore: 0.38, riskLevel: "low",        status: "declining",  platforms: ["YouTube","Reddit","Facebook"] },
  { id: "t9",  name: "Tonsil stone removal bobby pin",       firstDetected: "2025-07-01", posts: 177, riskScore: 0.91, riskLevel: "harmful",    status: "growing",    platforms: ["TikTok"] },
  { id: "t10", name: "Nose reshaping elastic bands",         firstDetected: "2025-06-05", posts: 433, riskScore: 0.76, riskLevel: "concerning", status: "peak",       platforms: ["TikTok","Instagram"] },
]

// ─── Cell renderers ───────────────────────────────────────────────────────────

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

function RiskBadge({ level, score }: { level: RiskLevel; score: number }) {
  if (level === "harmful") return (
    <Badge variant="destructive" className="gap-1 tabular-nums">
      <AlertTriangleIcon className="size-3" />{score.toFixed(2)}
    </Badge>
  )
  if (level === "concerning") return (
    <Badge className="bg-amber-500/10 text-amber-600 border-0 gap-1 tabular-nums dark:text-amber-400">
      <AlertTriangleIcon className="size-3" />{score.toFixed(2)}
    </Badge>
  )
  return <Badge variant="outline" className="gap-1 tabular-nums text-muted-foreground">{score.toFixed(2)}</Badge>
}

const statusStyles: Record<TrendStatus, string> = {
  peak:       "bg-red-500/10     text-red-600    dark:text-red-400    border-0",
  growing:    "bg-amber-500/10   text-amber-600  dark:text-amber-400  border-0",
  monitoring: "bg-blue-500/10    text-blue-600   dark:text-blue-400   border-0",
  declining:  "bg-muted          text-muted-foreground                border-0",
  resurgence: "bg-purple-500/10  text-purple-600 dark:text-purple-400 border-0",
}

function StatusBadge({ status }: { status: TrendStatus }) {
  return (
    <Badge className={statusStyles[status]}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  )
}

// ─── Column definitions ───────────────────────────────────────────────────────

const columns: ColumnDef<Trend>[] = [
  {
    accessorKey: "name",
    header: ({ column }) => (
      <button
        className="flex items-center gap-1 text-left font-medium hover:text-foreground transition-colors"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Trend Name
        {column.getIsSorted() === "asc" ? <ChevronUpIcon className="size-3.5" /> :
         column.getIsSorted() === "desc" ? <ChevronDownIcon className="size-3.5" /> :
         <ChevronsUpDownIcon className="size-3.5 opacity-40" />}
      </button>
    ),
    cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
  },
  {
    accessorKey: "firstDetected",
    header: ({ column }) => (
      <button
        className="flex items-center gap-1 font-medium hover:text-foreground transition-colors"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        First Detected
        {column.getIsSorted() === "asc" ? <ChevronUpIcon className="size-3.5" /> :
         column.getIsSorted() === "desc" ? <ChevronDownIcon className="size-3.5" /> :
         <ChevronsUpDownIcon className="size-3.5 opacity-40" />}
      </button>
    ),
    cell: ({ row }) => <span className="text-muted-foreground">{formatDate(row.original.firstDetected)}</span>,
    sortingFn: (a, b) =>
      new Date(a.original.firstDetected).getTime() - new Date(b.original.firstDetected).getTime(),
  },
  {
    accessorKey: "posts",
    header: ({ column }) => (
      <button
        className="flex items-center gap-1 font-medium hover:text-foreground transition-colors"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Posts
        {column.getIsSorted() === "asc" ? <ChevronUpIcon className="size-3.5" /> :
         column.getIsSorted() === "desc" ? <ChevronDownIcon className="size-3.5" /> :
         <ChevronsUpDownIcon className="size-3.5 opacity-40" />}
      </button>
    ),
    cell: ({ row }) => <span className="tabular-nums">{row.original.posts.toLocaleString()}</span>,
  },
  {
    accessorKey: "riskScore",
    header: ({ column }) => (
      <button
        className="flex items-center gap-1 font-medium hover:text-foreground transition-colors"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Risk Score
        {column.getIsSorted() === "asc" ? <ChevronUpIcon className="size-3.5" /> :
         column.getIsSorted() === "desc" ? <ChevronDownIcon className="size-3.5" /> :
         <ChevronsUpDownIcon className="size-3.5 opacity-40" />}
      </button>
    ),
    cell: ({ row }) => <RiskBadge level={row.original.riskLevel} score={row.original.riskScore} />,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  {
    accessorKey: "platforms",
    header: "Platforms",
    cell: ({ row }) => (
      <div className="flex flex-wrap gap-1">
        {row.original.platforms.map((p) => (
          <Badge key={p} variant="outline">{p}</Badge>
        ))}
      </div>
    ),
    enableSorting: false,
  },
  {
    id: "actions",
    header: "",
    cell: () => (
      <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
        <EyeIcon className="size-3.5" />
        View Details
      </Button>
    ),
    enableSorting: false,
  },
]

// ─── Main component ───────────────────────────────────────────────────────────

export function TrendsTable() {
  const [search, setSearch] = React.useState("")
  const [riskFilter, setRiskFilter] = React.useState("all")
  const [statusFilter, setStatusFilter] = React.useState("all")
  const [platformFilter, setPlatformFilter] = React.useState("all")
  const [postsFilter, setPostsFilter] = React.useState("all")
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: "firstDetected", desc: true },
  ])

  // Apply search + filter before table sees data
  const filtered = React.useMemo(() => {
    const q = search.toLowerCase()
    return ALL_TRENDS.filter((t) => {
      const matchSearch = !q || t.name.toLowerCase().includes(q) ||
        t.platforms.some((p) => p.toLowerCase().includes(q))
      const matchRisk = riskFilter === "all" || t.riskLevel === riskFilter
      const matchStatus = statusFilter === "all" || t.status === statusFilter
      const matchPlatform =
        platformFilter === "all" ||
        t.platforms.some((p) => p === platformFilter)
      const matchPosts =
        postsFilter === "all" ||
        (postsFilter === "<100" && t.posts < 100) ||
        (postsFilter === "100-500" && t.posts >= 100 && t.posts <= 500) ||
        (postsFilter === ">500" && t.posts > 500)
      return matchSearch && matchRisk && matchStatus && matchPlatform && matchPosts
    })
  }, [search, riskFilter, statusFilter, platformFilter, postsFilter])

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 8 } },
  })

  return (
    <div className="flex flex-col gap-4">
      {/* ── Row 1: Search bar (full width) ── */}
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

      {/* ── Row 2: Filters with labels ── */}
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
                <SelectItem value="harmful">Harmful</SelectItem>
                <SelectItem value="concerning">Concerning</SelectItem>
                <SelectItem value="low">Low</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        {/* Status */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Status</span>
          <Select value={statusFilter} onValueChange={(val) => setStatusFilter(val || "all")}>
            <SelectTrigger id="status-filter" className="w-36 h-8 text-sm">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="peak">Peak</SelectItem>
                <SelectItem value="growing">Growing</SelectItem>
                <SelectItem value="monitoring">Monitoring</SelectItem>
                <SelectItem value="declining">Declining</SelectItem>
                <SelectItem value="resurgence">Resurgence</SelectItem>
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
                <SelectItem value="TikTok">TikTok</SelectItem>
                <SelectItem value="Instagram">Instagram</SelectItem>
                <SelectItem value="YouTube">YouTube</SelectItem>
                <SelectItem value="Reddit">Reddit</SelectItem>
                <SelectItem value="Facebook">Facebook</SelectItem>
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

        {/* Sort */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Sort</span>
          <Select 
            value={sorting.length ? `${sorting[0].id}-${sorting[0].desc ? 'desc' : 'asc'}` : ''}
            onValueChange={(val) => {
              if (!val) return
              const [id, desc] = val.split('-')
              setSorting([{ id, desc: desc === 'desc' }])
            }}
          >
            <SelectTrigger id="sort-by" className="w-40 h-8 text-sm">
              <SelectValue placeholder="Sort by...">
                {sorting.length && sorting[0].id === 'firstDetected'
                  ? sorting[0].desc ? 'Newest First' : 'Oldest First'
                  : 'Sort by...'}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="firstDetected-desc">Newest First</SelectItem>
                <SelectItem value="firstDetected-asc">Oldest First</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

      </div>

      {/* ── Table — matches DataTable styling exactly ── */}
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

      {/* ── Pagination — same pattern as DataTable ── */}
      <div className="flex items-center justify-between px-1">
        <div className="flex-1 text-sm text-muted-foreground">
          {filtered.length === ALL_TRENDS.length
            ? `${ALL_TRENDS.length} trends`
            : `${filtered.length} of ${ALL_TRENDS.length} trends`}
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
                  {[8, 10, 20, 50].map((s) => (
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
