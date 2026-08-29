import * as React from "react"
import { Table } from "@/components/ui/table"
import { cn } from "@/lib/utils"

export function SidebarSection({
  title, description, children, icon: Icon, titleClassName,
}: {
  title: string
  description?: string
  icon?: React.ComponentType<{ className?: string }>
  titleClassName?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-1 px-1">
        <h2 className={cn("text-lg font-semibold flex items-center gap-2", titleClassName)}>
          {Icon && <Icon className="size-4" />}
          {title}
        </h2>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {children}
    </div>
  )
}

export function BorderedTable({ children, wrapperClassName }: { children: React.ReactNode; wrapperClassName?: string }) {
  return (
    <div className={cn("overflow-hidden rounded-lg border", wrapperClassName)}>
      <Table>{children}</Table>
    </div>
  )
}