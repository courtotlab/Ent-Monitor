import { Badge } from "@/components/ui/badge"
import { AlertTriangleIcon, AlertCircleIcon, ShieldCheckIcon } from "lucide-react"
import { type RiskLevel } from "@/lib/utils"

export function RiskBadge({ label, score }: { label?: string | RiskLevel; score: number }) {
  const pct = Math.round(score * 100)
  if (label === "HIGH" || score >= 0.7) {
    return (
      <Badge variant="destructive" className="tabular-nums bg-destructive/10 text-destructive border-0 hover:bg-destructive/20">
        <AlertTriangleIcon className="mr-1 size-3" />{pct}%
      </Badge>
    )
  }
  if (label === "MODERATE" || score >= 0.4) {
    return (
      <Badge className="tabular-nums bg-amber-500/10 text-amber-600 border-0 dark:text-amber-400 hover:bg-amber-500/20">
        <AlertCircleIcon className="mr-1 size-3" />{pct}%
      </Badge>
    )
  }
  return (
    <Badge className="tabular-nums bg-emerald-500/10 text-emerald-600 border-0 dark:text-emerald-400 hover:bg-emerald-500/20">
      <ShieldCheckIcon className="mr-1 size-3" />{pct}%
    </Badge>
  )
}
