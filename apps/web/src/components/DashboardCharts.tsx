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
import { useEffect, useState } from "react";
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

/* Chart.js takes colours as values, not CSS, so it cannot follow a theme swap
   on its own. Read the resolved custom properties instead of duplicating hex
   values here, and re-read them whenever the theme changes. */
type Palette = {
  name: string;
  ink: string;
  muted: string;
  grid: string;
  panel: string;
  forest: string;
  fern: string;
  stream: string;
  clay: string;
  honey: string;
  stone: string;
};

function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) =>
    cs.getPropertyValue(name).trim() || fallback;
  const explicit = document.documentElement.getAttribute("data-theme");
  const name =
    explicit ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  return {
    name,
    ink: v("--text", "#1f2a24"),
    muted: v("--muted", "#5a6a60"),
    grid: v("--chart-grid", "#e4e5da"),
    panel: v("--panel", "#fffefb"),
    forest: v("--accent", "#2e6f4e"),
    fern: v("--accent-2", "#4a8f63"),
    stream: v("--water", "#2f7a94"),
    clay: v("--danger", "#b0452f"),
    honey: v("--warn", "#b07d1d"),
    stone: v("--chart-neutral", "#a9b3ab"),
  };
}

/** Re-reads the palette on an explicit theme pick or an OS-level change. */
function useThemePalette(): Palette {
  const [palette, setPalette] = useState<Palette>(readPalette);

  useEffect(() => {
    const refresh = () => setPalette(readPalette());
    // data-theme flips on an explicit choice; the media query covers "system".
    const observer = new MutationObserver(refresh);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", refresh);
    return () => {
      observer.disconnect();
      mq.removeEventListener("change", refresh);
    };
  }, []);

  return palette;
}

function queueColor(palette: Palette): Record<string, string> {
  return {
    expedited: palette.clay,
    priority: palette.honey,
    standard: palette.stream,
    qc_sample: palette.fern,
    auto_clear: palette.stone,
  };
}

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

/** Inverted against the page so the tooltip reads as a raised surface in
 *  either theme. */
function tooltipFor(p: Palette) {
  return {
    backgroundColor: p.ink,
    titleColor: p.panel,
    bodyColor: p.panel,
    padding: 10,
    cornerRadius: 8,
    displayColors: true,
    boxPadding: 4,
  } as const;
}

/** Shared axis/plugin config. Typed per chart kind because Chart.js option
 *  types are invariant in the chart-type parameter. */
function baseOptions<T extends "bar" | "line">(p: Palette): ChartOptions<T> {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: tooltipFor(p),
    },
    scales: {
      x: {
        grid: { display: false },
        border: { color: p.grid },
        ticks: { color: p.muted },
      },
      y: {
        beginAtZero: true,
        grid: { color: p.grid },
        border: { display: false },
        ticks: { color: p.muted, precision: 0 },
      },
    },
  } as unknown as ChartOptions<T>;
}

export default function DashboardCharts({
  summary,
}: {
  summary: DashboardSummary;
}) {
  const palette = useThemePalette();
  const QUEUE_COLOR = queueColor(palette);
  const queues = (summary.by_queue || []).filter((q) => q.count > 0);
  const products = summary.by_product || [];
  const buckets = summary.score_buckets || [];
  const trend = summary.intake_trend || [];

  const funnel = [
    { label: "Awaiting review", value: summary.awaiting_review, color: palette.stream },
    { label: "Potential signal", value: summary.potential_signals, color: palette.honey },
    { label: "Confirmed signal", value: summary.confirmed_signals, color: palette.clay },
    { label: "Valid ICSR", value: summary.valid_icsr, color: palette.forest },
    { label: "Not relevant", value: summary.not_relevant, color: palette.stone },
    { label: "Deferred", value: summary.deferred, color: palette.fern },
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
              key={palette.name}
              data={{
                labels: queues.map((q) => QUEUE_LABEL[q.queue] || q.queue),
                datasets: [
                  {
                    data: queues.map((q) => q.count),
                    backgroundColor: queues.map(
                      (q) => QUEUE_COLOR[q.queue] || palette.stone
                    ),
                    borderColor: palette.panel,
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
                      color: palette.ink,
                      usePointStyle: true,
                      pointStyle: "circle",
                      padding: 14,
                      boxWidth: 8,
                    },
                  },
                  tooltip: tooltipFor(palette),
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
              key={palette.name}
              data={{
                labels: products.map((p) => p.product_name),
                datasets: [
                  {
                    label: "Articles",
                    data: products.map((p) => p.count),
                    backgroundColor: palette.forest,
                    hoverBackgroundColor: palette.fern,
                    borderRadius: 6,
                    maxBarThickness: 46,
                  },
                ],
              }}
              options={{ ...baseOptions<"bar">(palette), indexAxis: "y" as const }}
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
              key={palette.name}
              data={{
                labels: buckets.map((b) => b.band),
                datasets: [
                  {
                    label: "Articles",
                    data: buckets.map((b) => b.count),
                    backgroundColor: buckets.map((b) =>
                      b.band === "0.8-1.0"
                        ? palette.clay
                        : b.band === "0.6-0.8"
                        ? palette.honey
                        : palette.stream
                    ),
                    borderRadius: 6,
                    maxBarThickness: 54,
                  },
                ],
              }}
              options={baseOptions<"bar">(palette)}
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
              key={palette.name}
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
              options={{ ...baseOptions<"bar">(palette), indexAxis: "y" as const }}
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
              key={palette.name}
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
                    borderColor: palette.forest,
                    backgroundColor: "#2e6f4e22",
                    fill: true,
                    tension: 0.35,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    pointBackgroundColor: palette.forest,
                    borderWidth: 2,
                  },
                ],
              }}
              options={(() => {
                const o = baseOptions<"line">(palette);
                return {
                  ...o,
                  scales: {
                    ...o.scales,
                    x: {
                      ...o.scales?.x,
                      ticks: {
                        color: palette.muted,
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
