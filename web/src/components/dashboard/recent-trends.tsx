"use client"

import * as React from "react"
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table"

import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fetchRecentTrends, type TrendData } from "@/lib/api"
import { useApi } from "@/hooks/use-api"

import { formatDate, formatTrendName } from "@/lib/utils"
import { byDateField } from "@/lib/table-helpers"
import { RiskBadge } from "@/components/shared/risk-badge"
import { LifecycleBadge } from "@/components/shared/lifecycle-badge"
import { SortableHeader } from "@/components/shared/sortable-header"

// Column definitions

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
  },
  {
    accessorKey: "risk_score",
    header: ({ column }) => <SortableHeader column={column} label="Risk" />,
    cell: ({ row }) => <RiskBadge label={row.original.label} score={row.original.risk_score} />,
  },
  {
    accessorKey: "post_count",
    header: ({ column }) => <SortableHeader column={column} label="Posts" />,
    cell: ({ row }) => (
      <span className="tabular-nums">{row.original.post_count.toLocaleString()}</span>
    ),
  },
  {
    accessorKey: "lifecycle_status",
    header: "Lifecycle",
    cell: ({ row }) => <LifecycleBadge status={row.original.lifecycle_status} />,
  },
  {
    accessorKey: "platforms",
    header: "Platforms",
    cell: ({ row }) => (
      <div className="flex flex-wrap gap-1">
        {(row.original.platforms ?? []).map((p) => (
          <Badge key={p} variant="outline" className="text-xs">
            {p}
          </Badge>
        ))}
      </div>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "first_detected_at",
    header: ({ column }) => <SortableHeader column={column} label="Detected" />,
    cell: ({ row }) => (
      <span className="text-muted-foreground text-sm whitespace-nowrap">
        {formatDate(row.original.first_detected_at)}
      </span>
    ),
    sortingFn: byDateField("first_detected_at"),
  },
  {
    accessorKey: "last_seen_at",
    header: ({ column }) => <SortableHeader column={column} label="Last Seen" />,
    cell: ({ row }) => (
      <span className="text-muted-foreground text-sm whitespace-nowrap">
        {formatDate(row.original.last_seen_at)}
      </span>
    ),
    sortingFn: byDateField("last_seen_at"),
  },
]

// Main component

export function RecentTrendsTable() {
  const { data: trends, loading, error } = useApi<TrendData[]>(fetchRecentTrends)
  const data = React.useMemo(() => trends ?? [], [trends])
  const [sorting, setSorting] = React.useState<SortingState>([])

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (row) => row.trend_id,
  })

  return (
    <div className="flex flex-col gap-4 px-4 lg:px-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Recent Trends</h2>
          <p className="text-sm text-muted-foreground">
            Top 10 most recently classified or re-emerged trends
          </p>
        </div>
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
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
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
                  <div className="text-sm text-destructive">
                    Failed to load recent trends. Is the API running?
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
                  No trends classified yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
