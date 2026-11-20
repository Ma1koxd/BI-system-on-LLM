import type { Kpis } from "../types";
import { formatNumber } from "../format";

interface Metric {
  key: string;
  field: keyof Kpis;
  label: string;
  unit: string;
  note: (kpis: Kpis) => string;
}

const metrics: Metric[] = [
  {
    key: "output",
    field: "good",
    label: "Выпуск",
    unit: "шт.",
    note: kpis => `План ${formatNumber(kpis.plan)} шт.`
  },
  {
    key: "quality",
    field: "rate",
    label: "Доля брака",
    unit: "%",
    note: kpis => `${formatNumber(kpis.bad)} шт. брака`
  },
  {
    key: "down",
    field: "down",
    label: "Простои",
    unit: "мин",
    note: () => "Суммарно по станкам"
  },
  {
    key: "load",
    field: "load",
    label: "Загрузка",
    unit: "%",
    note: () => "По машино-часам"
  }
];

interface Props {
  kpis: Kpis;
  busy: boolean;
  onSelect: (key: string) => void;
}

export function KpiGrid({ kpis, busy, onSelect }: Props) {
  return (
    <section className="kpis" aria-label="Ключевые показатели">
      {metrics.map(metric => (
        <button
          key={metric.key}
          type="button"
          className="kpi"
          disabled={busy}
          onClick={() => onSelect(metric.key)}
        >
          <span className="kpi-label">{metric.label}</span>
          <span className="kpi-value">
            {formatNumber(kpis[metric.field])}
            <small>{metric.unit}</small>
          </span>
          <span className="kpi-note">{metric.note(kpis)}</span>
        </button>
      ))}
    </section>
  );
}
