import type { Report } from "../types";

interface Props {
  report: Report;
  busy: boolean;
  onGrain: (grain: "shift" | "hour") => void;
}

export function ChartPanel({ report, busy, onGrain }: Props) {
  const hourly = report.filters.grain === "hour";
  const unit = report.unit.endsWith(".") ? report.unit : `${report.unit}.`;

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <p className="eyebrow">Динамика</p>
          <h2>{report.metric_label}</h2>
        </div>
        <div className="segments">
          <button type="button" disabled={busy} aria-pressed={!hourly} onClick={() => onGrain("shift")}>
            По сменам
          </button>
          <button type="button" disabled={busy} aria-pressed={hourly} onClick={() => onGrain("hour")}>
            По часам
          </button>
        </div>
      </header>

      {report.series.length > 0 ? (
        <img
          className="chart"
          src={`data:image/png;base64,${report.chart.data}`}
          alt={report.chart.alt}
        />
      ) : (
        <p className="empty">Нет точек для выбранной выборки</p>
      )}

      <p className="note">
        {report.filters.compare === "week"
          ? "Сравнение с теми же часами и оборудованием семь суток назад."
          : `${report.metric_label} ${hourly ? "по часам" : "по сменам"}, ${unit}`}
      </p>
    </section>
  );
}
