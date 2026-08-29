import * as React from "react"
import { AppNavbar } from "./app-navbar"

interface PageShellProps {
  children: React.ReactNode
  activePage?: "Dashboard" | "Trends"
  contentClassName?: string
}

export function PageShell({ children, activePage, contentClassName }: PageShellProps) {
  return (
    <div className="flex min-h-svh flex-col bg-sidebar">
      <AppNavbar activePage={activePage} />
      <div className="flex flex-1 gap-0 p-2 pt-0 overflow-hidden">
        <main className="flex flex-1 flex-col overflow-y-auto rounded-2xl shadow-sm bg-background min-w-0">
          <div className="@container/main flex flex-1 flex-col gap-2">
            <div className={contentClassName ?? "flex flex-col gap-4 py-4 md:gap-6 md:py-6"}>
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
