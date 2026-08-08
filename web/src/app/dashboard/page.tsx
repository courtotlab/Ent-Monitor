import { AppNavbar } from "@/components/layout/app-navbar"
import { ChartAreaInteractive } from "@/components/dashboard/chart-area-interactive"
import { DataTable } from "@/components/dashboard/data-table"
import { SectionCards } from "@/components/dashboard/section-cards"

import data from "./data.json"

export default function Page() {
  return (
    <div className="flex min-h-svh flex-col bg-sidebar">
      <AppNavbar />
      <div className="flex flex-1 gap-0 p-2 pt-0 overflow-hidden">
        <main className="flex flex-1 flex-col overflow-y-auto rounded-2xl shadow-sm bg-background min-w-0">
          <div className="@container/main flex flex-1 flex-col gap-2">
            <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
              <div className="px-4 lg:px-6">
                <h1 className="text-2xl font-semibold">Dashboard</h1>
              </div>
              <SectionCards />
              <div className="px-4 lg:px-6">
                <ChartAreaInteractive />
              </div>
              <DataTable data={data} />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
