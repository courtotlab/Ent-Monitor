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
import {
  AlertTriangleIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronsUpDownIcon,
} from "lucide-react"

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

// Helpers

function formatDate(iso: string | null) {
  if (!iso) return "-"
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

function formatTrendName(trendId: string) {
  return trendId
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function LabelBadge({ label }: { label: string }) {
  if (label === "HIGH")
    return (
      <Badge
        variant="destructive"
        className="gap-1 tabular-nums"
      >
        <AlertTriangleIcon className="size-3" />
        High Risk
      </Badge>
    )
  if (label === "MODERATE")
    return (
      <Badge className="bg-amber-500/10 text-amber-600 border-0 gap-1 dark:text-amber-400">
        <AlertTriangleIcon className="size-3" />
        Moderate Risk
      </Badge>
    )
  return (
    <Badge
      variant="outline"
      className="gap-1 text-muted-foreground"
    >
      Low Risk
    </Badge>
  )
}

function RiskBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  if (score >= 0.7)
    return (
      <Badge
        variant="destructive"
        className="tabular-nums bg-destructive/10 text-destructive border-0 hover:bg-destructive/20"
      >
        {pct}%
      </Badge>
    )
  if (score >= 0.4)
    return (
      <Badge className="tabular-nums bg-amber-500/10 text-amber-600 border-0 dark:text-amber-400">
        {pct}%
      </Badge>
    )
  return (
    <Badge variant="outline" className="tabular-nums text-muted-foreground">
      {pct}%
    </Badge>
  )
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

// Sortable header helper 

function SortableHeader({column, label,}: {
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
  },
  {
    accessorKey: "label",
    header: "Label",
    cell: ({ row }) => <LabelBadge label={row.original.label} />,
  },
  {
    accessorKey: "risk_score",
    header: ({ column }) => <SortableHeader column={column} label="Risk" />,
    cell: ({ row }) => <RiskBadge score={row.original.risk_score} />,
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
    sortingFn: (a, b) => {
      const aDate = a.original.first_detected_at ? new Date(a.original.first_detected_at).getTime() : 0
      const bDate = b.original.first_detected_at ? new Date(b.original.first_detected_at).getTime() : 0
      return aDate - bDate
    },
  },
  {
    accessorKey: "last_seen_at",
    header: ({ column }) => <SortableHeader column={column} label="Last Seen" />,
    cell: ({ row }) => (
      <span className="text-muted-foreground text-sm whitespace-nowrap">
        {formatDate(row.original.last_seen_at)}
      </span>
    ),
    sortingFn: (a, b) => {
      const aDate = a.original.last_seen_at ? new Date(a.original.last_seen_at).getTime() : 0
      const bDate = b.original.last_seen_at ? new Date(b.original.last_seen_at).getTime() : 0
      return aDate - bDate
    },
  },
]

// Main component

export function DataTable() {
  const [data, setData] = React.useState<TrendData[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState(false)
  const [sorting, setSorting] = React.useState<SortingState>([])

  React.useEffect(() => {
    fetchRecentTrends()
      .then((trends) => {
        setData(trends)
        setLoading(false)
      })
      .catch((err) => {
        console.error("Failed to load recent trends:", err)
        setError(true)
        setLoading(false)
      })
  }, [])

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
