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
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
  EyeIcon,
  SearchIcon,
} from "lucide-react"
import { type DateRange } from "react-day-picker"

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
import { useApi } from "@/hooks/use-api"

import { formatDate, formatTrendName, parseUtcDate, pluralize } from "@/lib/utils"
import { byDateField } from "@/lib/table-helpers"
import { RiskBadge } from "@/components/shared/risk-badge"
import { LifecycleBadge } from "@/components/shared/lifecycle-badge"
import { VerificationBadge } from "@/components/shared/verification-badge"
import { SortableHeader } from "@/components/shared/sortable-header"
import { TrendsTableFilters, type TrendsTableFiltersState } from "./trends-table-filters"

const columns: ColumnDef<TrendData>[] = [
  {
    id: "trend_name",
    accessorFn: (row): string => row.trend_name || formatTrendName(row.trend_id),
    header: ({ column }) => <SortableHeader column={column} label="Trend Name" />,
    cell: ({ getValue }) => (
      <div className="min-w-[160px]">
        <span className="font-medium">{getValue<string>()}</span>
      </div>
    ),
    enableHiding: false,
  },
  {
    accessorKey: "first_detected_at",
    header: ({ column }) => <SortableHeader column={column} label="First Detected" />,
    cell: ({ row }) => <span className="text-muted-foreground">{formatDate(row.original.first_detected_at)}</span>,
    sortingFn: byDateField("first_detected_at"),
  },
  {
    accessorKey: "last_seen_at",
    header: ({ column }) => <SortableHeader column={column} label="Last Seen" />,
    cell: ({ row }) => <span className="text-muted-foreground">{formatDate(row.original.last_seen_at)}</span>,
    sortingFn: byDateField("last_seen_at"),
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

export function TrendsTable() {
  const { data, loading, error } = useApi<TrendData[]>(fetchAllTrends)
  const allTrends = React.useMemo<TrendData[]>(() => data ?? [], [data])

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
  const deferredSearch = React.useDeferredValue(search)

  const allPlatforms = React.useMemo(() => {
    const set = new Set<string>()
    allTrends.forEach((t) => (t.platforms ?? []).forEach((p) => set.add(p)))
    return Array.from(set).sort()
  }, [allTrends])

  const filtered = React.useMemo(() => {
    const q = deferredSearch.toLowerCase()
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
        const d = dStr ? parseUtcDate(dStr) : null
        if (d) {
          const from = new Date(Date.UTC(dateRange.from.getFullYear(), dateRange.from.getMonth(), dateRange.from.getDate(), 0, 0, 0, 0))
          if (d < from) matchDate = false
          if (dateRange.to) {
            const to = new Date(Date.UTC(dateRange.to.getFullYear(), dateRange.to.getMonth(), dateRange.to.getDate(), 23, 59, 59, 999))
            if (d > to) matchDate = false
          }
        } else {
          matchDate = false
        }
      }

      return matchSearch && matchRisk && matchStatus && matchPlatform && matchPosts && matchDate
    })
  }, [allTrends, deferredSearch, riskFilter, statusFilter, platformFilter, postsFilter, dateRange, dateFilterType])

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

  const isFiltered =
    search.length > 0 ||
    riskFilter !== "all" ||
    statusFilter !== "all" ||
    platformFilter !== "all" ||
    postsFilter !== "all" ||
    dateRange !== undefined

  const clearAll = () => {
    setSearch("")
    setRiskFilter("all")
    setStatusFilter("all")
    setPlatformFilter("all")
    setPostsFilter("all")
    setDateRange(undefined)
    setDateFilterType("first_detected_at")
  }

  const filterState: TrendsTableFiltersState = {
    search,
    riskFilter,
    statusFilter,
    platformFilter,
    postsFilter,
    dateRange,
    dateFilterType,
  }

  return (
    <div className="flex flex-col gap-4">
      <TrendsTableFilters
        state={filterState}
        setters={{
          setSearch,
          setRiskFilter,
          setStatusFilter,
          setPlatformFilter,
          setPostsFilter,
          setDateRange,
          setDateFilterType,
        }}
        allPlatforms={allPlatforms}
        isFiltered={isFiltered}
        onClear={clearAll}
      />

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

      <div className="flex items-center justify-between px-1">
        <div className="flex-1 text-sm text-muted-foreground">
          {loading ? "Loading…" : filtered.length === allTrends.length ? pluralize(allTrends.length, "trend") : `${filtered.length} of ${pluralize(allTrends.length, "trend")}`}
        </div>
        <div className="flex items-center gap-6">
          <div className="hidden items-center gap-2 lg:flex">
            <Label htmlFor="rows-per-page" className="text-sm font-medium">Rows per page</Label>
            <Select value={`${table.getState().pagination.pageSize}`} onValueChange={(v) => table.setPageSize(Number(v))}>
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
            <Button variant="outline" className="hidden size-8 lg:flex" size="icon" onClick={() => table.setPageIndex(0)} disabled={!table.getCanPreviousPage()}>
              <ChevronsLeftIcon />
            </Button>
            <Button variant="outline" className="size-8" size="icon" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
              <ChevronLeftIcon />
            </Button>
            <Button variant="outline" className="size-8" size="icon" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
              <ChevronRightIcon />
            </Button>
            <Button variant="outline" className="hidden size-8 lg:flex" size="icon" onClick={() => table.setPageIndex(table.getPageCount() - 1)} disabled={!table.getCanNextPage()}>
              <ChevronsRightIcon />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
