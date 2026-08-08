"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

// ─── Field ────────────────────────────────────────────────────────────────────

interface FieldProps extends React.ComponentProps<"div"> {
  orientation?: "vertical" | "horizontal"
  "data-invalid"?: boolean
}

function Field({ className, orientation = "vertical", ...props }: FieldProps) {
  return (
    <div
      data-slot="field"
      data-orientation={orientation}
      className={cn(
        "group/field flex",
        orientation === "horizontal"
          ? "flex-row items-center gap-4"
          : "flex-col gap-1.5",
        className
      )}
      {...props}
    />
  )
}

// ─── FieldLabel ───────────────────────────────────────────────────────────────

interface FieldLabelProps extends React.ComponentProps<"label"> {}

function FieldLabel({ className, ...props }: FieldLabelProps) {
  return (
    <label
      data-slot="field-label"
      className={cn(
        "text-sm font-medium leading-none select-none peer-disabled:cursor-not-allowed peer-disabled:opacity-50 group-data-[disabled=true]/field:pointer-events-none group-data-[disabled=true]/field:opacity-50",
        className
      )}
      {...props}
    />
  )
}

// ─── FieldDescription ─────────────────────────────────────────────────────────

function FieldDescription({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="field-description"
      className={cn("text-xs text-muted-foreground", className)}
      {...props}
    />
  )
}

// ─── FieldError ───────────────────────────────────────────────────────────────

interface FieldError {
  message?: string
}

interface FieldErrorProps extends React.ComponentProps<"p"> {
  errors?: (FieldError | undefined)[]
}

function FieldError({ className, errors, ...props }: FieldErrorProps) {
  const message = errors?.find((e) => e?.message)?.message
  if (!message) return null
  return (
    <p
      data-slot="field-error"
      role="alert"
      className={cn("text-xs font-medium text-destructive", className)}
      {...props}
    >
      {message}
    </p>
  )
}

// ─── FieldContent ─────────────────────────────────────────────────────────────

function FieldContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="field-content"
      className={cn("flex flex-1 flex-col gap-1", className)}
      {...props}
    />
  )
}

// ─── FieldGroup ───────────────────────────────────────────────────────────────

function FieldGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="field-group"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

// ─── FieldSet ─────────────────────────────────────────────────────────────────

function FieldSet({ className, ...props }: React.ComponentProps<"fieldset">) {
  return (
    <fieldset
      data-slot="field-set"
      className={cn("flex flex-col gap-3 border-0 p-0 m-0", className)}
      {...props}
    />
  )
}

// ─── FieldLegend ──────────────────────────────────────────────────────────────

interface FieldLegendProps extends React.ComponentProps<"legend"> {
  variant?: "default" | "label"
}

function FieldLegend({ className, variant = "default", ...props }: FieldLegendProps) {
  return (
    <legend
      data-slot="field-legend"
      className={cn(
        variant === "label"
          ? "text-sm font-medium leading-none"
          : "text-base font-semibold",
        "-ml-0.5 pb-2",
        className
      )}
      {...props}
    />
  )
}

export {
  Field,
  FieldLabel,
  FieldDescription,
  FieldError,
  FieldContent,
  FieldGroup,
  FieldSet,
  FieldLegend,
}
