export const LIFECYCLE_STATUSES = [
  "Emergence",
  "Growth",
  "Resurfacing",
  "Declining",
  "Latent",
  "Isolated incident",
] as const

export type LifecycleStatus = (typeof LIFECYCLE_STATUSES)[number]

export const VERIFICATION_STATUSES = ["CONFIRMED", "PROVISIONAL", "INSUFFICIENT_EVIDENCE"] as const
export type VerificationStatus = (typeof VERIFICATION_STATUSES)[number]
