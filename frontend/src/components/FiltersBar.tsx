import type { Report } from "../types";
import { formatNumber } from "../format";

const counts = [1, 5, 10, 14, 42];

function countLabel(count: number) {
  if (count === 1) return "Последняя смена";
  if (count === 42) return "Все 42 смены";
  return `Последние ${count} смен`;
}

interface Props {
  report: Report | null;
  busy: boolean;
  onLine: (line: string) => void;
  onCount: (count: number) => void;
  onReset: () => void;
}

export function FiltersBar({ report, busy, onLine, onCount, onReset }: Props) {
  const filters = report?.filters;
  const count = filters?.count ?? 5;
  const dates = Boolean(filters?.since || filters?.until);
  const selected = dates ? "dates" : String(count);
  const options = counts.includes(count) ? counts : [...counts, count].sort((a, b) => a - b);
  const chips = [
    filters && filters.shift !== "Все" ? filters.shift : "",
    filters && filters.machine !== "Все" ? filters.machine : "",
    filters && filters.status !== "Все" ? `Заказ · ${filters.status}` : "",
    filters && filters.defect !== "Все" ? `Дефект · ${filters.defect}` : "",
    filters?.lag ? `Отставание ≥ ${formatNumber(filters.threshold)} %` : "",
    filters && filters.top > 0 ? `Топ-${filters.top}` : "",
    filters?.compare === "week" ? "Сравнение с прошлой неделей" : "",
    filters && filters.offset > 0 ? "Неделей ранее" : "",
    filters && filters.tool === "downtime_events" && filters.min > 0
      ? `Простой > ${filters.min} мин`
      : ""
  ].filter(Boolean);
  const period = dates
    ? [filters?.since || "Начало витрины", filters?.until || "Конец витрины"].join(" — ")
    : `Завершённые смены: ${count}`;

  return (
    <>
      <div className="filters">
        <label>
          <span>Линия</span>
          <select
            value={filters?.line ?? "Все"}
            disabled={busy}
            onChange={event => onLine(event.target.value)}
          >
            <option value="Все">Все линии</option>
            <option value="А">Линия А</option>
            <option value="Б">Линия Б</option>
          </select>
        </label>
        <label>
          <span>Период</span>
          <select
            value={selected}
            disabled={busy}
            onChange={event => {
              if (event.target.value !== "dates") onCount(Number(event.target.value));
            }}
          >
            {options.map(value => (
              <option key={value} value={value}>{countLabel(value)}</option>
            ))}
            {dates && <option value="dates" disabled>Выбранные даты</option>}
          </select>
        </label>
      </div>
      <p className="period">
        {period} · {filters?.line === "Все" || !filters ? "Линии А и Б" : `Линия ${filters.line}`}
      </p>
      {chips.length > 0 && (
        <div className="chips">
          {chips.map(chip => <span key={chip}>{chip}</span>)}
          <button type="button" disabled={busy} onClick={onReset}>Сбросить фильтры</button>
        </div>
      )}
    </>
  );
}
