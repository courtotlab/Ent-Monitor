import { Badge } from "@/components/ui/badge"
import { type LifecycleStatus } from "@/lib/constants"

const lifecycleStyles: Record<LifecycleStatus, string> = {
  Emergence: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-0",
  Growth: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-0",
  Resurfacing: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-0",
  Declining: "bg-muted text-muted-foreground border-0",
  Latent: "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-0",
  "Isolated incident": "bg-muted text-muted-foreground border-0",
}

export function LifecycleBadge({ status }: { status: LifecycleStatus }) {
  return (
    <Badge className={lifecycleStyles[status]}>
      {status}
    </Badge>
  )
}

