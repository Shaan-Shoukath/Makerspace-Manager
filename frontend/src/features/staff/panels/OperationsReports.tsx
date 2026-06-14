import { useState } from "react";

import { downloadStaffFile } from "../../../lib/api";
import {
  BarChart,
  DataState,
  PieChart,
  ReportTable,
  StatCards,
  chartRows,
  reportRows,
  type ReportRows,
} from "./OperationsReportsParts";
import { Panel, type Makerspace, useStaffGet } from "./shared";

type Summary = {
  products: number;
  assets: number;
  active_loans: number;
  available_quantity: number;
  issued_quantity: number;
  damaged_quantity: number;
  missing_quantity: number;
};

type PrintingReport = {
  totals: Record<string, number>;
  printer_hours: {
    printer_id: number;
    printer_name: string;
    completed_requests: number;
    hours: number;
    makerspace_id?: number;
  }[];
  filament_used: {
    spool_id: number;
    material: string;
    color: string;
    grams_used: number;
    remaining_grams: number;
    makerspace_id?: number;
  }[];
  filament_by_brand: { brand: string; grams_used: number; spools: number }[];
  top_requesters: {
    requester_id: number;
    requester: string;
    requests: number;
    items: number;
    makerspace_id?: number;
  }[];
  total_grams_used: number;
  filament_estimated_by_period: {
    by_month: { period: string; grams: number }[];
    by_day: { period: string; grams: number }[];
    by_hour: { period: string; grams: number }[];
  };
};

type PeriodKey = "month" | "day" | "hour";

const exportReports = ["taken-items", "active-loans", "returns", "damaged-lost"] as const;
const periods: { key: PeriodKey; label: string; dataKey: keyof PrintingReport["filament_estimated_by_period"] }[] = [
  { key: "month", label: "Month", dataKey: "by_month" },
  { key: "day", label: "Day", dataKey: "by_day" },
  { key: "hour", label: "Hour", dataKey: "by_hour" },
];

// Print-status pie slices, in a stable display order.
const statusPie: { key: keyof PrintingReport["totals"]; label: string }[] = [
  { key: "completed", label: "Completed" },
  { key: "printing", label: "Printing" },
  { key: "pending", label: "Pending" },
  { key: "accepted", label: "Accepted" },
  { key: "failed", label: "Failed" },
  { key: "rejected", label: "Rejected" },
];

export function OperationsReports({
  makerspace,
  isSuperadmin,
  printingOnly = false,
}: {
  makerspace: Makerspace;
  isSuperadmin: boolean;
  printingOnly?: boolean;
}) {
  const [allMakerspaces, setAllMakerspaces] = useState(false);
  const [period, setPeriod] = useState<PeriodKey>("month");
  const aggregate = isSuperadmin && allMakerspaces;
  const scopeKey = aggregate ? "all" : makerspace.id;
  const analyticsBase = aggregate ? "/admin/analytics" : `/admin/makerspace/${makerspace.id}/analytics`;
  const reportsBase = aggregate ? "/admin/reports" : `/admin/makerspace/${makerspace.id}/reports`;
  // printing routes are mounted under /api/v1/printing/ (not /api/v1/admin/).
  const printingPath = aggregate ? "/printing/admin/printing/reports" : `/printing/admin/makerspace/${makerspace.id}/printing/reports`;

  // Print managers (printingOnly) lack VIEW_INVENTORY, so the hardware analytics
  // endpoints would 403. Disable those queries entirely rather than render empty,
  // erroring panels — the printing report is the only one they can see.
  const hardwareEnabled = !printingOnly;
  const summary = useStaffGet<Summary>(["operations-report", "summary", scopeKey], `${analyticsBase}/summary`, hardwareEnabled);
  const mostLent = useStaffGet<ReportRows>(["operations-report", "most-lent", scopeKey], `${analyticsBase}/most-lent`, hardwareEnabled);
  const topBorrowers = useStaffGet<ReportRows>(["operations-report", "top-borrowers", scopeKey], `${analyticsBase}/top-borrowers`, hardwareEnabled);
  const damagedLost = useStaffGet<ReportRows>(["operations-report", "damaged-lost", scopeKey], `${analyticsBase}/damaged-lost`, hardwareEnabled);
  const recentlyAdded = useStaffGet<ReportRows>(["operations-report", "recently-added", scopeKey], `${analyticsBase}/recently-added`, hardwareEnabled);
  const printing = useStaffGet<PrintingReport>(["operations-report", "printing", scopeKey], printingPath);

  const activePeriod = periods.find((item) => item.key === period) ?? periods[0];
  const filamentRows = printing.data?.filament_estimated_by_period[activePeriod.dataKey] ?? [];
  const scopeLabel = aggregate ? "all makerspaces" : makerspace.name;

  const statusRows = statusPie
    .map((item) => ({ label: item.label, value: printing.data?.totals[item.key] ?? 0 }))
    .filter((row) => row.value > 0);
  const brandRows = (printing.data?.filament_by_brand ?? [])
    .slice(0, 8)
    .map((row) => ({ label: row.brand, value: row.grams_used }));

  function exportReport(report: string, format: "csv" | "xlsx") {
    downloadStaffFile(`${reportsBase}/${report}/export?format=${format}`, `${aggregate ? "all-makerspaces-" : ""}${report}.${format}`);
  }

  return (
    <div className="space-y-4">
      <Panel title="Reports">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-ink">
              {printingOnly ? "3D printing reporting" : "Operations reporting"} for {scopeLabel}
            </p>
            <p className="text-xs text-muted">
              {printingOnly
                ? "Print jobs, printer hours, and filament usage."
                : "Inventory movement, borrower activity, exceptions, and print usage."}
            </p>
          </div>
          {isSuperadmin ? (
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                className="h-4 w-4 accent-current"
                checked={allMakerspaces}
                onChange={(event) => setAllMakerspaces(event.target.checked)}
              />
              All makerspaces
            </label>
          ) : null}
        </div>
        {!printingOnly ? (
          <DataState loading={summary.isLoading} error={summary.error} empty={!summary.data}>
            <StatCards
              stats={[
                ["Products", summary.data?.products],
                ["Assets", summary.data?.assets],
                ["Active loans", summary.data?.active_loans],
                ["Available", summary.data?.available_quantity],
                ["Issued", summary.data?.issued_quantity],
                ["Damaged", summary.data?.damaged_quantity],
                ["Missing", summary.data?.missing_quantity],
              ]}
            />
          </DataState>
        ) : null}
      </Panel>

      {!printingOnly ? (
      <>
      <Panel title="Exports">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {exportReports.map((report) => (
            <div key={report} className="rounded-md border border-line bg-bg p-3">
              <p className="text-sm font-semibold capitalize text-ink">{report.replace(/-/g, " ")}</p>
              <div className="mt-3 flex gap-2">
                <button className="desk-button" type="button" onClick={() => exportReport(report, "csv")}>
                  CSV
                </button>
                <button className="desk-button" type="button" onClick={() => exportReport(report, "xlsx")}>
                  XLSX
                </button>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Most lent">
          <DataState loading={mostLent.isLoading} error={mostLent.error} empty={!reportRows(mostLent.data).length}>
            <BarChart rows={chartRows(mostLent.data, "product_name", "times_lent")} valueLabel="loans" />
            <ReportTable data={mostLent.data} />
          </DataState>
        </Panel>

        <Panel title="Top borrowers">
          <DataState loading={topBorrowers.isLoading} error={topBorrowers.error} empty={!reportRows(topBorrowers.data).length}>
            <BarChart rows={chartRows(topBorrowers.data, "holder", "requests")} valueLabel="requests" />
            <ReportTable data={topBorrowers.data} />
          </DataState>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Damaged / lost">
          <DataState loading={damagedLost.isLoading} error={damagedLost.error} empty={!reportRows(damagedLost.data).length}>
            <ReportTable data={damagedLost.data} />
          </DataState>
        </Panel>

        <Panel title="Recently added">
          <DataState loading={recentlyAdded.isLoading} error={recentlyAdded.error} empty={!reportRows(recentlyAdded.data).length}>
            <ReportTable data={recentlyAdded.data} />
          </DataState>
        </Panel>
      </div>
      </>
      ) : null}

      <Panel title="3D printing">
        <DataState loading={printing.isLoading} error={printing.error} empty={!printing.data}>
          <div className="space-y-5">
            <StatCards
              stats={[
                ["Total requests", printing.data?.totals.total_requests],
                ["Completed", printing.data?.totals.completed],
                ["Printing", printing.data?.totals.printing],
                ["Pending", printing.data?.totals.pending],
                ["Accepted", printing.data?.totals.accepted],
                ["Failed", printing.data?.totals.failed],
                ["Rejected", printing.data?.totals.rejected],
                ["Spool grams used", printing.data?.total_grams_used],
              ]}
            />

            <div className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-md border border-line bg-bg p-3">
                <h3 className="mb-3 text-sm font-semibold text-ink">Requests by status</h3>
                <PieChart rows={statusRows} valueLabel="" />
              </div>
              <div className="rounded-md border border-line bg-bg p-3">
                <h3 className="mb-3 text-sm font-semibold text-ink">Filament share by brand</h3>
                <PieChart rows={brandRows} valueLabel="g" />
              </div>
            </div>

            <div>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">Estimated filament</h3>
                <div className="flex rounded-md border border-line bg-bg p-1">
                  {periods.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      className={`rounded px-3 py-1 text-xs font-semibold ${period === item.key ? "bg-surface text-accent" : "text-muted"}`}
                      onClick={() => setPeriod(item.key)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
              <BarChart rows={filamentRows.map((row) => ({ label: row.period, value: row.grams }))} valueLabel="g" />
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <div>
                <h3 className="mb-2 text-sm font-semibold text-ink">Printer hours</h3>
                <ReportTable
                  data={{
                    rows: [
                      aggregate
                        ? ["makerspace_id", "printer", "completed_requests", "hours"]
                        : ["printer", "completed_requests", "hours"],
                      ...(printing.data?.printer_hours ?? []).map((row) =>
                        aggregate
                          ? [row.makerspace_id ?? "", row.printer_name, row.completed_requests, row.hours]
                          : [row.printer_name, row.completed_requests, row.hours],
                      ),
                    ],
                  }}
                />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold text-ink">Filament used</h3>
                <ReportTable
                  data={{
                    rows: [
                      aggregate
                        ? ["makerspace_id", "material", "color", "grams_used", "remaining_grams"]
                        : ["material", "color", "grams_used", "remaining_grams"],
                      ...(printing.data?.filament_used ?? []).map((row) =>
                        aggregate
                          ? [row.makerspace_id ?? "", row.material, row.color, row.grams_used, row.remaining_grams]
                          : [row.material, row.color, row.grams_used, row.remaining_grams],
                      ),
                    ],
                  }}
                />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold text-ink">Filament by brand</h3>
                <BarChart
                  rows={(printing.data?.filament_by_brand ?? [])
                    .slice(0, 8)
                    .map((row) => ({ label: row.brand, value: row.grams_used }))}
                  valueLabel="g"
                />
                <ReportTable
                  data={{
                    rows: [
                      ["brand", "grams_used", "spools"],
                      ...(printing.data?.filament_by_brand ?? []).map((row) => [
                        row.brand,
                        row.grams_used,
                        row.spools,
                      ]),
                    ],
                  }}
                />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold text-ink">Top requesters</h3>
                <BarChart
                  rows={(printing.data?.top_requesters ?? [])
                    .slice(0, 8)
                    .map((row) => ({ label: row.requester, value: row.requests }))}
                  valueLabel=" reqs"
                />
                <ReportTable
                  data={{
                    rows: [
                      aggregate
                        ? ["makerspace_id", "requester", "requests", "items"]
                        : ["requester", "requests", "items"],
                      ...(printing.data?.top_requesters ?? []).map((row) =>
                        aggregate
                          ? [row.makerspace_id ?? "", row.requester, row.requests, row.items]
                          : [row.requester, row.requests, row.items],
                      ),
                    ],
                  }}
                />
              </div>
            </div>
          </div>
        </DataState>
      </Panel>
    </div>
  );
}
