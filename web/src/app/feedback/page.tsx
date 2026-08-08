"use client"

import { AppNavbar } from "@/components/layout/app-navbar"
import { TrendReportForm } from "@/components/feedback/trend-report-form"
import { ProblemReportForm } from "@/components/feedback/problem-report-form"

export default function FeedbackPage() {
  return (
    <div className="flex min-h-svh flex-col bg-sidebar">
      <AppNavbar activePage="Feedback" />

      <div className="flex flex-1 gap-0 p-2 pt-0 overflow-hidden">
        <main className="flex flex-1 flex-col overflow-y-auto rounded-2xl shadow-sm bg-background min-w-0">
          <div className="@container/main flex flex-1 flex-col gap-2">
            <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
              {/* Page header */}
              <div className="px-4 lg:px-6">
                <h1 className="text-2xl font-semibold">Feedback &amp; Reporting Center</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Submit trend reports and problem reports to our team.
                </p>
              </div>

              {/* Two-column form layout */}
              <div className="px-4 lg:px-6">
                <div className="grid grid-cols-1 gap-6 @xl/main:grid-cols-2">
                  <TrendReportForm />
                  <ProblemReportForm />
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
