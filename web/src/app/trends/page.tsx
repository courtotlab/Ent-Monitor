import { AppNavbar } from "@/components/layout/app-navbar"
import { TrendsTable } from "@/components/report/trends-table"

export default function TrendsPage() {
  return (
    <div className="flex min-h-svh flex-col bg-sidebar">
      <AppNavbar />

      <div className="flex flex-1 gap-0 p-2 pt-0 overflow-hidden">
        <main className="flex flex-1 flex-col overflow-y-auto rounded-2xl shadow-sm bg-background min-w-0">
          <div className="@container/main flex flex-1 flex-col gap-2">
            <div className="flex flex-col gap-6 py-4 md:py-6 px-4 lg:px-6">
              {/* Page header */}
              <div>
                <h1 className="text-2xl font-semibold">Trends</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Monitor and review all detected health misinformation trends.
                </p>
              </div>

              {/* Table with search + filters */}
              <TrendsTable />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
