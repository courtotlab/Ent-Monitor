"use client"

import { format } from "date-fns"
import { CalendarIcon, SlidersHorizontalIcon, XIcon } from "lucide-react"
import { type DateRange } from "react-day-picker"

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { LIFECYCLE_STATUSES } from "@/lib/constants"

export interface TrendsTableFiltersState {
  search: string
  riskFilter: string
  statusFilter: string
  platformFilter: string
  postsFilter: string
  dateRange: DateRange | undefined
  dateFilterType: "first_detected_at" | "last_seen_at"
}

export interface TrendsTableFiltersProps {
  state: TrendsTableFiltersState
  setters: {
    setSearch: (v: string) => void
    setRiskFilter: (v: string) => void
    setStatusFilter: (v: string) => void
    setPlatformFilter: (v: string) => void
    setPostsFilter: (v: string) => void
    setDateRange: (v: DateRange | undefined) => void
    setDateFilterType: (v: "first_detected_at" | "last_seen_at") => void
  }
  allPlatforms: string[]
  isFiltered: boolean
  onClear: () => void
}

const RISK_OPTIONS = [
  { value: "all", label: "All levels" },
  { value: "HIGH", label: "High Risk" },
  { value: "MODERATE", label: "Moderate Risk" },
  { value: "LOW", label: "Low Risk" },
]

const POSTS_OPTIONS = [
  { value: "all", label: "All volume" },
  { value: "<100", label: "Under 100" },
  { value: "100-500", label: "100 - 500" },
  { value: ">500", label: "Over 500" },
]

function DateRangeControl({ state, setters, compact }: { state: TrendsTableFiltersState; setters: TrendsTableFiltersProps["setters"]; compact?: boolean }) {
  const { dateRange, dateFilterType } = state
  return (
    <div className="flex items-center gap-2">
      <span className={`${compact ? "text-sm" : "text-sm"} font-medium text-muted-foreground ${compact ? "w-20 shrink-0" : "whitespace-nowrap"}`}>
        Date
      </span>
      <Popover>
        <PopoverTrigger
          render={
            <Button
              variant="ghost"
              className={`justify-between text-left font-normal ${compact ? "h-10 px-3 text-sm flex-1" : "h-8 px-3 text-sm rounded-2xl border border-transparent bg-input/50 hover:bg-input/80 hover:text-accent-foreground"} ${dateRange?.from ? (compact ? "" : "w-[220px]") : compact ? "text-muted-foreground" : "w-[165px]"}`}
            >
              <div className="flex items-center truncate">
                <CalendarIcon className="mr-2 size-4 shrink-0" />
                {dateRange?.from ? (
                  <span className="truncate">
                    {!compact && (
                      <span className="text-muted-foreground mr-1">
                        {dateFilterType === "first_detected_at" ? "First:" : "Last:"}
                      </span>
                    )}
                    {dateRange.to ? (
                      <>{format(dateRange.from, "LLL dd")} - {format(dateRange.to, "LLL dd")}</>
                    ) : (
                      format(dateRange.from, "LLL dd, y")
                    )}
                  </span>
                ) : (
                  <span className="truncate">{compact ? "Select range" : "Select range..."}</span>
                )}
              </div>
            </Button>
          }
        />
        <PopoverContent className="w-auto p-0" align="start">
          {compact ? (
            <Calendar mode="range" defaultMonth={dateRange?.from} selected={dateRange} onSelect={setters.setDateRange} numberOfMonths={1} />
          ) : (
            <>
              <Calendar mode="range" defaultMonth={dateRange?.from} selected={dateRange} onSelect={setters.setDateRange} numberOfMonths={1} className="md:hidden" />
              <Calendar mode="range" defaultMonth={dateRange?.from} selected={dateRange} onSelect={setters.setDateRange} numberOfMonths={2} className="hidden md:block" />
            </>
          )}
          <div className="p-3 border-t flex items-center justify-between bg-muted/20">
            <div className="flex items-center gap-3">
              {!compact && <span className="text-sm text-muted-foreground">Apply to:</span>}
              <div className="flex bg-muted/60 p-1 rounded-md">
                <button
                  className={`h-7 px-3 text-xs font-medium rounded-sm transition-colors ${
                    dateFilterType === "first_detected_at"
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                  onClick={() => setters.setDateFilterType("first_detected_at")}
                >
                  {compact ? "First" : "First Detected"}
                </button>
                <button
                  className={`h-7 px-3 text-xs font-medium rounded-sm transition-colors ${
                    dateFilterType === "last_seen_at"
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                  onClick={() => setters.setDateFilterType("last_seen_at")}
                >
                  {compact ? "Last" : "Last Seen"}
                </button>
              </div>
            </div>
            {dateRange?.from && (
              <Button variant="ghost" size="sm" className="h-8 px-3 text-xs text-muted-foreground hover:text-foreground" onClick={() => setters.setDateRange(undefined)}>
                Clear
              </Button>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}

export function TrendsTableFilters({ state, setters, allPlatforms, isFiltered, onClear }: TrendsTableFiltersProps) {
  const { search, riskFilter, statusFilter, platformFilter, postsFilter, dateRange } = state
  const activeCount = [
    riskFilter !== "all",
    statusFilter !== "all",
    platformFilter !== "all",
    postsFilter !== "all",
    dateRange !== undefined,
  ].filter(Boolean).length

  return (
    <>
      {/* Row 1: Search bar (full width) */}
      <div className="relative flex items-center h-8 w-full rounded-2xl border border-transparent bg-input/50 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30 transition-[color,box-shadow] duration-200">
        <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <input
          id="trends-search"
          type="search"
          placeholder="Search trends, platforms…"
          className="flex-1 bg-transparent pl-8 pr-2.5 py-1 text-sm outline-none min-w-0 text-foreground placeholder:text-muted-foreground"
          value={search}
          onChange={(e) => setters.setSearch(e.target.value)}
        />
      </div>

      {/* Desktop filter row */}
      <div className="hidden md:flex items-center gap-4 flex-wrap">
        <SelectRow label="Risk" value={riskFilter} onChange={setters.setRiskFilter} options={RISK_OPTIONS} />
        <SelectRow
          label="Lifecycle"
          value={statusFilter}
          onChange={setters.setStatusFilter}
          options={[{ value: "all", label: "All statuses" }, ...LIFECYCLE_STATUSES.map((s) => ({ value: s, label: s }))]}
        />
        <SelectRow
          label="Platform"
          value={platformFilter}
          onChange={setters.setPlatformFilter}
          options={[{ value: "all", label: "All platforms" }, ...allPlatforms.map((p) => ({ value: p, label: p }))]}
        />
        <SelectRow label="Posts" value={postsFilter} onChange={setters.setPostsFilter} options={POSTS_OPTIONS} />
        <DateRangeControl state={state} setters={setters} />
        {isFiltered && (
          <Button variant="ghost" onClick={onClear} className="h-8 px-2 lg:px-3 text-sm text-muted-foreground hover:text-foreground">
            Clear filters
            <XIcon className="ml-2 size-4" />
          </Button>
        )}
      </div>

      {/* Mobile filter dropdown */}
      <div className="md:hidden flex items-center gap-2">
        <Popover>
          <PopoverTrigger
            render={
              <Button variant="ghost" className="h-8 px-3 text-sm text-muted-foreground hover:text-foreground rounded-2xl border border-transparent bg-input/50 hover:bg-input/80">
                <SlidersHorizontalIcon className="mr-1.5 size-4" />
                Filters
                {isFiltered && (
                  <span className="ml-2 inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded-full bg-primary text-primary-foreground text-xs font-medium">
                    {activeCount}
                  </span>
                )}
              </Button>
            }
          />
          <PopoverContent className="w-[300px] p-0" align="start">
            <div className="p-3.5 space-y-3.5">
              <SelectRow compact label="Risk" value={riskFilter} onChange={setters.setRiskFilter} options={RISK_OPTIONS} />
              <SelectRow
                compact
                label="Lifecycle"
                value={statusFilter}
                onChange={setters.setStatusFilter}
                options={[{ value: "all", label: "All statuses" }, ...LIFECYCLE_STATUSES.map((s) => ({ value: s, label: s }))]}
              />
              <SelectRow
                compact
                label="Platform"
                value={platformFilter}
                onChange={setters.setPlatformFilter}
                options={[{ value: "all", label: "All platforms" }, ...allPlatforms.map((p) => ({ value: p, label: p }))]}
              />
              <SelectRow compact label="Posts" value={postsFilter} onChange={setters.setPostsFilter} options={POSTS_OPTIONS} />
              <DateRangeControl compact state={state} setters={setters} />
              {isFiltered && (
                <Button variant="ghost" onClick={onClear} className="w-full h-10 px-3 text-sm text-muted-foreground hover:text-foreground justify-center">
                  Clear all filters
                  <XIcon className="ml-2 size-4" />
                </Button>
              )}
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </>
  )
}

interface SelectRowProps {
  label: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  compact?: boolean
}

function SelectRow({ label, value, onChange, options, compact }: SelectRowProps) {
  return (
    <div className="flex items-center gap-2">
      <span className={`${compact ? "text-sm w-20 shrink-0" : "text-sm whitespace-nowrap"} font-medium text-muted-foreground`}>
        {label}
      </span>
      <Select value={value} onValueChange={(v) => onChange(v || "all")}>
        <SelectTrigger className={compact ? "h-10 text-sm flex-1" : "w-36 h-8 text-sm"}>
          <SelectValue placeholder="All" />
        </SelectTrigger>
        <SelectContent>
          {compact ? (
            options.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))
          ) : (
            <SelectGroup>
              {options.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectGroup>
          )}
        </SelectContent>
      </Select>
    </div>
  )
}
