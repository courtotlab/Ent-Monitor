import { Badge } from "@/components/ui/badge"
import { type VerificationStatus } from "@/lib/constants"

const verificationStyles: Record<VerificationStatus, string> = {
  CONFIRMED: "bg-green-500/10 text-green-600 dark:text-green-400 border-0",
  PROVISIONAL: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-0",
  INSUFFICIENT_EVIDENCE: "bg-muted text-muted-foreground border-0",
}

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  return (
    <Badge className={verificationStyles[status]}>
      {status}
    </Badge>
  )
}

