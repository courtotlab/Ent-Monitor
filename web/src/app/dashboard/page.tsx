import { RiskChart } from "@/components/dashboard/risk-chart"
import { RecentTrendsTable } from "@/components/dashboard/recent-trends"
import { StatsCards } from "@/components/dashboard/stats-cards"
import { PageShell } from "@/components/layout/page-shell"

export default function Page() {
  return (
    <PageShell activePage="Dashboard">
      <div className="px-4 lg:px-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
      </div>
      <StatsCards />
      <div className="px-4 lg:px-6">
        <RiskChart />
      </div>
      <RecentTrendsTable />
    </PageShell>
  )
}
