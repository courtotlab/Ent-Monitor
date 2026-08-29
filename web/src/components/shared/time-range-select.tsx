"use client"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { ChevronDownIcon } from "lucide-react"
import { TIME_RANGE_LABELS, type TimeRange } from "@/lib/chart-helpers"

interface TimeRangeSelectProps {
  value: TimeRange
  onChange: (value: TimeRange) => void
  className?: string
}

export function TimeRangeSelect({ value, onChange, className }: TimeRangeSelectProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className={`w-40 justify-between ${className ?? ""}`}
          >
            {TIME_RANGE_LABELS[value]}
            <ChevronDownIcon className="size-4 opacity-50" />
          </Button>
        }
      />
      <DropdownMenuContent className="w-40 rounded-xl" align="end">
        {(Object.keys(TIME_RANGE_LABELS) as Array<keyof typeof TIME_RANGE_LABELS>).map((key) => (
          <DropdownMenuItem key={key} onClick={() => onChange(key)}>
            {TIME_RANGE_LABELS[key]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
