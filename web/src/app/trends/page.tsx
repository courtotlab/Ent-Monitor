import { TrendsTable } from "@/components/trends/trends-table"
import { PageShell } from "@/components/layout/page-shell"

export default function TrendsPage() {
  return (
    <PageShell activePage="Trends" contentClassName="flex flex-col gap-6 py-4 md:py-6 px-4 lg:px-6">
      <div>
        <h1 className="text-2xl font-semibold">Trends</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Monitor and review all detected health misinformation trends.
        </p>
      </div>
      <TrendsTable />
    </PageShell>
  )
}
