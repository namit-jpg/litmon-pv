import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  type ChartOptions,
} from "chart.js";
import { Bar, Doughnut, Line } from "react-chartjs-2";
import type { DashboardSummary } from "../api";

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip
);

/* Palette mirrors styles.css so charts read as part of the same system.
   Queue colours match the queue pills exactly: clay, honey, stream, fern. */
const INK = "#1f2a24";
const MUTED = "#5a6a60";
const GRID = "#e4e5da";
const FOREST = "#2e6f4e";
const FERN = "#4a8f63";
const STREAM = "#2f7a94";
const CLAY = "#b0452f";
const HONEY = "#b07d1d";
const STONE = "#a9b3ab";

const QUEUE_COLOR: Record<string, string> = {
  expedited: CLAY,
  priority: HONEY,
  standard: STREAM,
  qc_sample: FERN,
  auto_clear: STONE,
};
const QUEUE_LABEL: Record<string, string> = {
  expedited: "Expedited",
  priority: "Priority",
  standard: "Standard",
  qc_sample: "QC sample",
  auto_clear: "Auto-clear",
};

ChartJS.defaults.font.family =
  'ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif';
ChartJS.defaults.font.size = 12;
ChartJS.defaults.color = MUTED;

const tooltipStyle = {
  backgroundColor: "#1f2a24",
  titleColor: "#fffefb",
  bodyColor: "#e8eee9",
  padding: 10,
  cornerRadius: 8,
  displayColors: true,
  boxPadding: 4,
} as const;

/** Shared axis/plugin config. Typed per chart kind because Chart.js option
 *  types are invariant in the chart-type parameter. */
function baseOptions<T extends "bar" | "line">(): ChartOptions<T> {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: tooltipStyle,
    },
    scales: {
      x: {
        grid: { display: false },
        border: { color: GRID },
        ticks: { color: MUTED },
      },
      y: {
        beginAtZero: true,
        grid: { color: GRID },
        border: { display: false },
        ticks: { color: MUTED, precision: 0 },
      },
    },
  } as unknown as ChartOptions<T>;
}

export default function DashboardCharts({
  summary,
}: {
  summary: DashboardSummary;
}) {
  const queues = (summary.by_queue || []).filter((q) => q.count > 0);
  const products = summary.by_product || [];
  const buckets = summary.score_buckets || [];
  const trend = summary.intake_trend || [];

  const funnel = [
    { label: "Awaiting review", value: summary.awaiting_review, color: STREAM },
    { label: "Potential signal", value: summary.potential_signals, color: HONEY },
    { label: "Confirmed signal", value: summary.confirmed_signals, color: CLAY },
    { label: "Valid ICSR", value: summary.valid_icsr, color: FOREST },
    { label: "Not relevant", value: summary.not_relevant, color: STONE },
    { label: "Deferred", value: summary.deferred, color: FERN },
  ];

  const hasQueue = queues.length > 0;
  const hasProducts = products.length > 0;
  const hasBuckets = buckets.some((b) => b.count > 0);
  const hasTrend = trend.some((t) => t.count > 0);
  const hasFunnel = funnel.some((f) => f.value > 0);

  return (
    <div className="chart-grid">
      <section className="card chart-card">
        <h2>Triage queue mix</h2>
        <p className="chart-sub">Open work by SLA queue</p>
        <div className="chart-box chart-box-doughnut">
          {hasQueue ? (
            <Doughnut
              data={{
                labels: queues.map((q) => QUEUE_LABEL[q.queue] || q.queue),
                datasets: [
                  {
                    data: queues.map((q) => q.count),
                    backgroundColor: queues.map(
                      (q) => QUEUE_COLOR[q.queue] || STONE
                    ),
                    borderColor: "#fffefb",
                    borderWidth: 3,
                    hoverOffset: 8,
                  },
                ],
              }}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                cutout: "62%",
                plugins: {
                  legend: {
                    position: "bottom",
                    labels: {
                      color: INK,
                      usePointStyle: true,
                      pointStyle: "circle",
                      padding: 14,
                      boxWidth: 8,
                    },
                  },
                  tooltip: tooltipStyle,
                },
              }}
            />
          ) : (
            <p className="muted chart-empty">No open triaged work.</p>
          )}
        </div>
      </section>

      <section className="card chart-card">
        <h2>Literature by product</h2>
        <p className="chart-sub">Articles screened per monitored product</p>
        <div className="chart-box">
          {hasProducts ? (
            <Bar
              data={{
                labels: products.map((p) => p.product_name),
                datasets: [
                  {
                    label: "Articles",
                    data: products.map((p) => p.count),
                    backgroundColor: FOREST,
                    hoverBackgroundColor: FERN,
                    borderRadius: 6,
                    maxBarThickness: 46,
                  },
                ],
              }}
              options={{ ...baseOptions<"bar">(), indexAxis: "y" as const }}
            />
          ) : (
            <p className="muted chart-empty">No literature yet.</p>
          )}
        </div>
      </section>

      <section className="card chart-card">
        <h2>AI composite score spread</h2>
        <p className="chart-sub">
          Screening confidence distribution — higher bands drive expedited review
        </p>
        <div className="chart-box">
          {hasBuckets ? (
            <Bar
              data={{
                labels: buckets.map((b) => b.band),
                datasets: [
                  {
                    label: "Articles",
                    data: buckets.map((b) => b.count),
                    backgroundColor: buckets.map((b) =>
                      b.band === "0.8-1.0"
                        ? CLAY
                        : b.band === "0.6-0.8"
                        ? HONEY
                        : STREAM
                    ),
                    borderRadius: 6,
                    maxBarThickness: 54,
                  },
                ],
              }}
              options={baseOptions<"bar">()}
            />
          ) : (
            <p className="muted chart-empty">Nothing screened yet.</p>
          )}
        </div>
      </section>

      <section className="card chart-card">
        <h2>Review workflow</h2>
        <p className="chart-sub">
          Where the monitored literature currently sits
        </p>
        <div className="chart-box">
          {hasFunnel ? (
            <Bar
              data={{
                labels: funnel.map((f) => f.label),
                datasets: [
                  {
                    label: "Articles",
                    data: funnel.map((f) => f.value),
                    backgroundColor: funnel.map((f) => f.color),
                    borderRadius: 6,
                    maxBarThickness: 34,
                  },
                ],
              }}
              options={{ ...baseOptions<"bar">(), indexAxis: "y" as const }}
            />
          ) : (
            <p className="muted chart-empty">No review activity yet.</p>
          )}
        </div>
      </section>

      <section className="card chart-card chart-card-wide">
        <h2>Publication volume</h2>
        <p className="chart-sub">
          Monitored literature by publication week, last 8 weeks
        </p>
        <div className="chart-box">
          {hasTrend ? (
            <Line
              data={{
                labels: trend.map((t) =>
                  new Date(t.date + "T00:00:00").toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                  })
                ),
                datasets: [
                  {
                    label: "Published",
                    data: trend.map((t) => t.count),
                    borderColor: FOREST,
                    backgroundColor: "#2e6f4e22",
                    fill: true,
                    tension: 0.35,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    pointBackgroundColor: FOREST,
                    borderWidth: 2,
                  },
                ],
              }}
              options={(() => {
                const o = baseOptions<"line">();
                return {
                  ...o,
                  scales: {
                    ...o.scales,
                    x: {
                      ...o.scales?.x,
                      ticks: {
                        color: MUTED,
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 8,
                      },
                    },
                  },
                } as ChartOptions<"line">;
              })()}
            />
          ) : (
            <p className="muted chart-empty">
              No publication dates in the last 30 days.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
