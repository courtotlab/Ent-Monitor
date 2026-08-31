import { addDays, formatISO } from "date-fns"

export type TimeRange = "7d" | "30d" | "90d"

export const TIME_RANGE_DAYS: Record<TimeRange, number> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
}

export const TIME_RANGE_LABELS: Record<TimeRange, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 3 months",
}

interface DatePoint {
  date: string
}

export function filterByTimeRange<T extends DatePoint>(
  data: T[],
  timeRange: TimeRange,
  fallbackEndDate?: string,
  emptyTemplate?: Omit<T, "date">
): T[] {
  const isDataEmpty = !data || data.length === 0;
  if (isDataEmpty && !emptyTemplate) return [];

  const referenceDate = fallbackEndDate 
    ? fallbackEndDate 
    : !isDataEmpty 
      ? data[data.length - 1].date 
      : formatISO(new Date(), { representation: "date" });

  const endDate = new Date(referenceDate.split("T")[0]);
  const startDate = addDays(endDate, -TIME_RANGE_DAYS[timeRange]);
  
  const dataMap = new Map((data || []).map((item) => [item.date.split("T")[0], item]));

  const zeroKeys = emptyTemplate ?? (Object.fromEntries(
    Object.keys(data[0] as object).filter((k) => k !== "date").map((k) => [k, 0]),
  ) as Omit<T, "date">);

  const result: T[] = [];
  for (let d = startDate; d <= endDate; d = addDays(d, 1)) {
    const dateStr = formatISO(d, { representation: "date" });
    result.push((dataMap.get(dateStr) ?? { date: dateStr, ...zeroKeys }) as T);
  }
  return result;
}

export function formatChartDate(value: string): string {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  })
}

export function AreaGradient({ id, colorVar }: { id: string; colorVar: string }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="5%" stopColor={`var(--color-${colorVar})`} stopOpacity={0.8} />
      <stop offset="95%" stopColor={`var(--color-${colorVar})`} stopOpacity={0.1} />
    </linearGradient>
  )
}
