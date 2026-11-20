import { useEffect, useState } from "react";
import type { Report } from "../types";
import { formatNumber } from "../format";

const PAGE_SIZE = 6;

const titles: Record<string, string> = {
  plan_shortfalls: "Смены с отставанием",
  hourly_output: "Динамика по часам",
  machine_ranking: "Рейтинг станков",
  downtime_events: "Журнал простоев",
  defect_breakdown: "Брак по причинам",
  compare_week: "Сравнение с прошлой неделей"
};

const viewTitles: Record<string, string> = {
  machine: "Показатели по станкам",
  line: "Показатели по линиям",
  shift: "Показатели по сменам"
};

interface Props {
  report: Report;
}

export function TablePanel({ report }: Props) {
  const [page, setPage] = useState(0);
  const { columns, rows } = report.table;
  const pages = Math.ceil(rows.length / PAGE_SIZE);
  const current = Math.min(page, Math.max(pages - 1, 0));
  const start = current * PAGE_SIZE;
  const visible = rows.slice(start, start + PAGE_SIZE);
  const title = titles[report.tool] ?? viewTitles[report.filters.view] ?? "Результаты анализа";

  useEffect(() => {
    setPage(0);
  }, [report]);

  function exportJson() {
    const blob = new Blob([JSON.stringify(report.table, null, 2)], {
      type: "application/json;charset=utf-8"
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `takt-${report.tool}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <p className="eyebrow">Детализация</p>
          <h2>{title}</h2>
        </div>
        <div className="table-actions">
          <span className="row-count">Строк: {rows.length}</span>
          <button type="button" className="button" onClick={exportJson} disabled={!rows.length}>
            Скачать JSON
          </button>
        </div>
      </header>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map(column => (
                <th key={column.key} scope="col">
                  {column.label}{column.unit ? `, ${column.unit}` : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, index) => (
              <tr key={start + index}>
                {columns.map(column => {
                  const value = row[column.key];
                  const tone = column.key === "deviation" && typeof value === "number"
                    ? value <= -10 ? "bad" : value >= 0 ? "good" : ""
                    : "";
                  return (
                    <td key={column.key} className={tone}>
                      {formatNumber(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td className="empty" colSpan={Math.max(columns.length, 1)}>
                  Нет подходящих записей
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <nav className="pager" aria-label="Страницы таблицы">
          <span>{start + 1}–{Math.min(start + PAGE_SIZE, rows.length)} из {rows.length}</span>
          <div>
            <button type="button" className="button" disabled={current === 0} onClick={() => setPage(current - 1)}>
              Назад
            </button>
            <button type="button" className="button" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>
              Далее
            </button>
          </div>
        </nav>
      )}
    </section>
  );
}
