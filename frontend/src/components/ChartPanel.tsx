import type { Report } from "../types";

interface Props {
  report: Report;
  busy: boolean;
  onGrain: (grain: "shift" | "hour") => void;
}

const WIDTH = 900;
const HEIGHT = 300;
const MARGIN = { top: 16, right: 16, bottom: 34, left: 44 };

export function ChartPanel({ report, busy, onGrain }: Props) {
  const hourly = report.filters.grain === "hour";
  const points = report.series;
  const values = points.flatMap(point => [point.actual, point.plan, point.previous])
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const min = values.length ? Math.min(...values, 0) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const span = max - min || 1;
  const innerWidth = WIDTH - MARGIN.left - MARGIN.right;
  const innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const xAt = (index: number) =>
    MARGIN.left + (points.length <= 1 ? innerWidth / 2 : (index / (points.length - 1)) * innerWidth);
  const yAt = (value: number) => MARGIN.top + innerHeight - ((value - min) / span) * innerHeight;

  const polyline = (key: "actual" | "plan" | "previous") =>
    points
      .map((point, index) => (point[key] === null ? null : `${xAt(index)},${yAt(point[key] as number)}`))
      .filter(Boolean)
      .join(" ");

  const ticks = [0, 0.25, 0.5, 0.75, 1].map(step => min + span * step);
  const labelIndexes = points.length <= 8
    ? points.map((_, index) => index)
    : [0, Math.floor((points.length - 1) / 2), points.length - 1];

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

      {points.length > 0 ? (
        <svg className="chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={report.metric_label}>
          {ticks.map((tick, index) => (
            <g key={index}>
              <line
                x1={MARGIN.left}
                x2={WIDTH - MARGIN.right}
                y1={yAt(tick)}
                y2={yAt(tick)}
                className="grid-line"
              />
              <text x={MARGIN.left - 6} y={yAt(tick) + 4} textAnchor="end" className="axis-label">
                {Math.round(tick)}
              </text>
            </g>
          ))}
          {points.map((point, index) =>
            point.downtime > 0 ? (
              <circle
                key={`down-${index}`}
                cx={xAt(index)}
                cy={HEIGHT - MARGIN.bottom + 12}
                r={3}
                className="marker downtime"
              />
            ) : null
          )}
          {polyline("previous") && (
            <polyline points={polyline("previous")} className="series previous" />
          )}
          {polyline("plan") && (
            <polyline points={polyline("plan")} className="series plan" />
          )}
          {polyline("actual") && (
            <polyline points={polyline("actual")} className="series actual" />
          )}
          {points.map((point, index) =>
            point.actual !== null ? (
              <circle key={`dot-${index}`} cx={xAt(index)} cy={yAt(point.actual)} r={2.5} className="dot" />
            ) : null
          )}
          {labelIndexes.map(index => (
            <text key={`label-${index}`} x={xAt(index)} y={HEIGHT - 8} textAnchor="middle" className="axis-label">
              {String(points[index].label).replace(" · ", " ")}
            </text>
          ))}
          <text x={MARGIN.left} y={12} className="axis-label">{report.unit}</text>
        </svg>
      ) : (
        <p className="empty">Нет точек для выбранной выборки</p>
      )}

      <div className="legend">
        <span className="legend-item actual">Факт</span>
        <span className="legend-item plan">План</span>
        <span className="legend-item previous">Неделей ранее</span>
        {points.some(point => point.downtime > 0) && (
          <span className="legend-item downtime">Час с простоем</span>
        )}
      </div>

      <p className="note">
        {report.filters.compare === "week"
          ? "Сравнение с теми же часами и оборудованием семь суток назад."
          : `${report.metric_label} ${hourly ? "по часам" : "по сменам"}, ${report.unit}.`}
      </p>
    </section>
  );
}