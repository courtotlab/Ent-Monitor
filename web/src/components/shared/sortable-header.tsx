"use client"

import { ChevronUpIcon, ChevronDownIcon, ChevronsUpDownIcon } from "lucide-react"
import type { Column } from "@tanstack/react-table"

interface SortableHeaderProps<TData> {
  column: Column<TData>
  label: string
}

export function SortableHeader<TData>({ column, label }: SortableHeaderProps<TData>) {
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
