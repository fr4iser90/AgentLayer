import type { Dispatch, SetStateAction } from "react";
import { useMemo } from "react";
import { Bar, Doughnut, Line, Pie } from "react-chartjs-2";
import { useTranslation } from "react-i18next";
import i18n from "../../../i18n/config";

import "./chartRegister";

import { getPath, setPath } from "../dashboardDataPaths";

export type ChartTypeName = "line" | "bar" | "pie" | "doughnut";

const PALETTE_BG = [
  "rgba(56, 189, 248, 0.55)",
  "rgba(167, 139, 250, 0.55)",
  "rgba(52, 211, 153, 0.55)",
  "rgba(251, 191, 36, 0.55)",
  "rgba(244, 114, 182, 0.55)",
  "rgba(148, 163, 184, 0.5)",
];

const PALETTE_BORDER = [
  "rgb(56, 189, 248)",
  "rgb(167, 139, 250)",
  "rgb(52, 211, 153)",
  "rgb(251, 191, 36)",
  "rgb(244, 114, 182)",
  "rgb(148, 163, 184)",
];

export type ChartDataState = {
  chartType: ChartTypeName;
  labels: string[];
  series: { label: string; data: number[] }[];
};

export function readChartData(raw: unknown): ChartDataState {
  const d =
    raw && typeof raw === "object" && !Array.isArray(raw)
      ? (raw as Record<string, unknown>)
      : {};
  const ct = String(d.chartType ?? "line").toLowerCase();
  const chartType: ChartTypeName =
    ct === "bar" || ct === "pie" || ct === "doughnut" ? ct : "line";
  let labels = Array.isArray(d.labels) ? d.labels.map((x) => String(x)) : [];
  const serRaw = Array.isArray(d.series) ? d.series : [];
  const series: { label: string; data: number[] }[] = serRaw.map((s) => {
    const o = s && typeof s === "object" && !Array.isArray(s) ? (s as Record<string, unknown>) : {};
    const data = Array.isArray(o.data) ? o.data.map((n) => Number(n) || 0) : [];
    return { label: String(o.label ?? i18n.t("dashboard:chartSeriesDefault")), data };
  });
  if (series.length === 0) {
    series.push({ label: i18n.t("dashboard:chartSeriesOne"), data: [0, 0, 0] });
  }
  const need = Math.max(
    labels.length,
    ...series.map((s) => s.data.length),
    1
  );
  while (labels.length < need) labels.push(i18n.t("dashboard:chartAxisLabel", { n: labels.length + 1 }));
  labels = labels.slice(0, need);
  for (const s of series) {
    while (s.data.length < need) s.data.push(0);
    s.data = s.data.slice(0, need);
  }
  if (!labels.length) labels = ["A"];
  return { chartType, labels, series };
}

function patchChart(
  dp: string,
  setData: Dispatch<SetStateAction<Record<string, unknown>>>,
  partial: Partial<ChartDataState> | ((prev: ChartDataState) => ChartDataState)
) {
  setData((d) => {
    const cur = readChartData(dp ? getPath(d, dp) : undefined);
    const next = typeof partial === "function" ? partial(cur) : { ...cur, ...partial };
    return setPath(d, dp, next as unknown);
  });
}

const baseOpts = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      labels: { color: "#a3a3a3", font: { size: 11 } },
    },
  },
} as const;

const cartesianOpts = {
  ...baseOpts,
  scales: {
    x: {
      ticks: { color: "#a3a3a3" },
      grid: { color: "rgba(255,255,255,0.06)" },
    },
    y: {
      ticks: { color: "#a3a3a3" },
      grid: { color: "rgba(255,255,255,0.06)" },
    },
  },
};

const radialOpts = {
  ...baseOpts,
};

export function ChartBlockBody(props: {
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  readOnly: boolean;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { dp, data, setData, sectionTitle, readOnly } = props;
  const chart = readChartData(dp ? getPath(data, dp) : undefined);

  const chartData = useMemo(() => {
    const { chartType, labels, series } = chart;
    if (chartType === "pie" || chartType === "doughnut") {
      const s0 = series[0] ?? { label: "Werte", data: [1] };
      const dataArr = s0.data.length ? s0.data : [0];
      const labs = labels.slice(0, dataArr.length);
      while (labs.length < dataArr.length) labs.push(`L${labs.length + 1}`);
      return {
        labels: labs,
        datasets: [
          {
            label: s0.label,
            data: dataArr,
            backgroundColor: dataArr.map((_, i) => PALETTE_BG[i % PALETTE_BG.length]),
            borderColor: dataArr.map((_, i) => PALETTE_BORDER[i % PALETTE_BORDER.length]),
            borderWidth: 1,
          },
        ],
      };
    }
    return {
      labels,
      datasets: series.map((s, i) => ({
        label: s.label,
        data: s.data,
        borderColor: PALETTE_BORDER[i % PALETTE_BORDER.length],
        backgroundColor:
          chartType === "bar"
            ? PALETTE_BG.map((c) => c.replace("0.55", "0.35"))
            : "rgba(56, 189, 248, 0.12)",
        fill: chartType === "line",
        tension: 0.25,
      })),
    };
  }, [chart]);

  const options = chart.chartType === "pie" || chart.chartType === "doughnut" ? radialOpts : cartesianOpts;

  const el =
    chart.chartType === "bar" ? (
      <Bar data={chartData} options={options} />
    ) : chart.chartType === "pie" ? (
      <Pie data={chartData} options={options} />
    ) : chart.chartType === "doughnut" ? (
      <Doughnut data={chartData} options={options} />
    ) : (
      <Line data={chartData} options={options} />
    );

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
      <h3 className="mb-3 text-sm font-medium text-white">{sectionTitle}</h3>
      <div className="h-56 min-h-[200px] w-full md:h-64">{el}</div>
      {!readOnly ? (
        <div className="dashboard-grid-no-drag mt-4 space-y-3 border-t border-white/5 pt-4">
          <div>
            <label className="mb-1 block text-[10px] uppercase text-surface-muted">{t("dashboard:chartTypeLabel")}</label>
            <select
              className="w-full rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100"
              value={chart.chartType}
              onChange={(e) =>
                patchChart(dp, setData, {
                  chartType: e.target.value as ChartTypeName,
                })
              }
            >
              <option value="line">{t("dashboard:chartTypeLine")}</option>
              <option value="bar">{t("dashboard:chartTypeBar")}</option>
              <option value="pie">{t("dashboard:chartTypePie")}</option>
              <option value="doughnut">{t("dashboard:chartTypeDoughnut")}</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] uppercase text-surface-muted">
              {t("dashboard:chartCategoriesLabel")}
            </label>
            <textarea
              className="min-h-[72px] w-full rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100"
              value={chart.labels.join("\n")}
              onChange={(e) => {
                const labels = e.target.value.split("\n").map((s) => s.trimEnd());
                patchChart(dp, setData, (prev) => {
                  const need = Math.max(
                    labels.length,
                    ...prev.series.map((s) => s.data.length),
                    1
                  );
                  const nextLabels = [...labels];
                  while (nextLabels.length < need) nextLabels.push(`L${nextLabels.length + 1}`);
                  const series = prev.series.map((s) => {
                    const d = [...s.data];
                    while (d.length < need) d.push(0);
                    return { ...s, data: d.slice(0, need) };
                  });
                  return { ...prev, labels: nextLabels.slice(0, need), series };
                });
              }}
            />
          </div>
          {chart.series.map((s, si) => (
            <div key={si} className="rounded-lg border border-white/5 bg-black/20 p-2">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-[10px] text-surface-muted">{t("dashboard:chartSeriesN", { n: si + 1 })}</span>
                {chart.series.length > 1 ? (
                  <button
                    type="button"
                    className="text-[10px] text-red-400 hover:underline"
                    onClick={() =>
                      patchChart(dp, setData, (prev) => ({
                        ...prev,
                        series: prev.series.filter((_, i) => i !== si),
                      }))
                    }
                  >
                    {t("dashboard:remove")}
                  </button>
                ) : null}
              </div>
              <input
                type="text"
                className="mb-2 w-full rounded border border-surface-border bg-black/40 px-2 py-1 text-xs text-white"
                placeholder={t("dashboard:chartSeriesLabelPlaceholder")}
                value={s.label}
                onChange={(e) =>
                  patchChart(dp, setData, (prev) => {
                    const series = [...prev.series];
                    series[si] = { ...series[si], label: e.target.value };
                    return { ...prev, series };
                  })
                }
              />
              <label className="mb-1 block text-[10px] text-surface-muted">
                {t("dashboard:chartValuesLabel")}
              </label>
              <input
                type="text"
                className="w-full rounded border border-surface-border bg-black/40 px-2 py-1 text-xs text-neutral-100"
                value={s.data.join(", ")}
                onChange={(e) => {
                  const parts = e.target.value.split(",").map((x) => Number(x.trim()) || 0);
                  patchChart(dp, setData, (prev) => {
                    const need = Math.max(prev.labels.length, parts.length, 1);
                    let labels = [...prev.labels];
                    while (labels.length < need) labels.push(i18n.t("dashboard:chartAxisLabel", { n: labels.length + 1 }));
                    labels = labels.slice(0, need);
                    const series = [...prev.series];
                    const d = [...parts];
                    while (d.length < need) d.push(0);
                    series[si] = { ...series[si], data: d.slice(0, need) };
                    return { ...prev, labels, series };
                  });
                }}
              />
            </div>
          ))}
          {(chart.chartType === "line" || chart.chartType === "bar") && chart.series.length < 6 ? (
            <button
              type="button"
              className="rounded-md bg-white/10 px-2 py-1 text-xs text-white hover:bg-white/15"
              onClick={() =>
                patchChart(dp, setData, (prev) => {
                  const need = Math.max(prev.labels.length, 1);
                  const zeros = Array.from({ length: need }, () => 0);
                  return {
                    ...prev,
                    series: [
                      ...prev.series,
                      { label: `Serie ${prev.series.length + 1}`, data: zeros },
                    ],
                  };
                })
              }
            >
              {t("dashboard:chartAddSeries")}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function readSparklineValues(raw: unknown): number[] {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const v = (raw as Record<string, unknown>).values;
    if (Array.isArray(v)) return v.map((x) => (Number.isFinite(Number(x)) ? Number(x) : 0));
  }
  return [0, 2, 1, 4, 3];
}

export function SparklineBlockBody(props: {
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  readOnly: boolean;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { dp, data, setData, sectionTitle, readOnly } = props;
  const values = readSparklineValues(dp ? getPath(data, dp) : undefined);

  const chartData = useMemo(
    () => ({
      labels: values.map((_, i) => String(i)),
      datasets: [
        {
          data: values.length ? values : [0],
          borderColor: "rgb(56, 189, 248)",
          backgroundColor: "rgba(56, 189, 248, 0.15)",
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    }),
    [values]
  );

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: true } },
      scales: {
        x: { display: false },
        y: { display: false },
      },
      elements: { point: { radius: 0 } },
    }),
    []
  );

  const patchVals = (nums: number[]) => {
    setData((d) => setPath(d, dp, { values: nums }));
  };

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-3">
      <p className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">{sectionTitle}</p>
      <div className="mt-2 h-16 w-full">
        <Line data={chartData} options={options} />
      </div>
      {!readOnly ? (
        <div className="dashboard-grid-no-drag mt-3">
          <label className="mb-1 block text-[10px] text-surface-muted">{t("dashboard:sparklineValuesLabel")}</label>
          <input
            type="text"
            className="w-full rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100"
            value={values.join(", ")}
            onChange={(e) => {
              const nums = e.target.value
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean)
                .map((x) => Number(x) || 0);
              patchVals(nums.length ? nums : [0]);
            }}
          />
        </div>
      ) : null}
    </section>
  );
}
