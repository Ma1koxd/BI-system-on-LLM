import { useCallback, useEffect, useRef, useState } from "react";
import { ask, buildReport, getConfig } from "./api";
import { ChartPanel } from "./components/ChartPanel";
import { ChatPanel } from "./components/ChatPanel";
import { FiltersBar } from "./components/FiltersBar";
import { KpiGrid } from "./components/KpiGrid";
import { TablePanel } from "./components/TablePanel";
import type { Config, Message, Report } from "./types";

const START_QUESTION = "Как цех выполнил план за последние 5 смен?";
const START_TOOL = "shift_summary";

const sections = [
  { id: "shift", label: "Сводка" },
  { id: "machine", label: "Оборудование" },
  { id: "events", label: "Простои" }
] as const;

type Section = (typeof sections)[number]["id"];

const titles: Record<Section, string> = {
  shift: "Производственная сводка",
  machine: "Анализ оборудования",
  events: "Анализ простоев"
};

export default function App() {
  const [report, setReport] = useState<Report | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [question, setQuestion] = useState("");
  const controller = useRef<AbortController | null>(null);

  const run = useCallback(async (
    load: (signal: AbortSignal) => Promise<Report>,
    label: string,
    options: { reset?: boolean } = {}
  ) => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setBusy(true);
    setError("");
    if (options.reset) setMessages([]);
    setMessages(previous => [...previous, { role: "user", text: label }]);

    try {
      const result = await load(current.signal);
      if (controller.current !== current) return;
      setReport(result);
      setMessages(previous => [
        ...previous,
        { role: "bot", text: result.summary, tips: result.recommendations }
      ]);
    } catch (caught) {
      if (current.signal.aborted || controller.current !== current) return;
      const text = caught instanceof Error ? caught.message : "Неизвестная ошибка.";
      setError(text);
      setMessages(previous => [...previous, { role: "bot", text }]);
    } finally {
      if (controller.current === current) {
        controller.current = null;
        setBusy(false);
      }
    }
  }, []);

  const request = useCallback((
    tool: string,
    args: object,
    label: string,
    context = report?.filters ?? {}
  ) => {
    run(signal => buildReport(tool, args, context, signal), label);
  }, [report, run]);

  const submit = useCallback((text: string) => {
    const value = text.trim();
    if (!value) return;
    setQuestion("");
    run(signal => ask(value, report?.filters ?? {}, signal), value);
  }, [report, run]);

  const reset = useCallback(() => {
    setQuestion("");
    run(signal => buildReport(START_TOOL, {}, {}, signal), START_QUESTION, { reset: true });
  }, [run]);

  useEffect(() => {
    getConfig().then(setConfig).catch(() => setConfig(null));
    run(signal => buildReport(START_TOOL, {}, {}, signal), START_QUESTION, { reset: true });
  }, [run]);

  const section: Section = report?.tool === "downtime_events" || report?.filters.view === "events"
    ? "events"
    : report?.filters.view === "machine" || report?.tool === "machine_ranking"
      ? "machine"
      : "shift";

  function openSection(next: Section) {
    if (next === "events") {
      request("downtime_events", { view: "events", metric: "down", min: 0, lag: false, top: 0 }, titles[next]);
    } else {
      request("shift_summary", { view: next, metric: "output", lag: false, top: 0, min: 0 }, titles[next]);
    }
  }

  function selectMetric(key: string) {
    const view = ["shift", "line", "machine"].includes(report?.filters.view ?? "")
      ? report!.filters.view
      : "shift";
    if (key === "down") {
      request("downtime_events", { metric: "down", min: 0 }, "Простои");
    } else if (key === "load") {
      request("equipment_load", { metric: "load", view: "machine" }, "Загрузка оборудования");
    } else {
      request("shift_summary", { metric: key, view, lag: false, top: 0, min: 0 },
        key === "quality" ? "Доля брака" : "Выпуск продукции");
    }
  }

  function changeLine(line: string) {
    request(report?.filters.tool ?? START_TOOL, { line, machine: "Все" },
      line === "Все" ? "Все линии" : `Линия ${line}`);
  }

  function changeCount(count: number) {
    request(report?.filters.tool ?? START_TOOL, { count, since: "", until: "", offset: 0 },
      `Смен: ${count}`);
  }

  return (
    <div className="page">
      <header className="topbar">
        <button type="button" className="brand" onClick={reset}>
          Такт <span>BI</span>
        </button>
        <nav aria-label="Разделы">
          {sections.map(item => (
            <button
              key={item.id}
              type="button"
              aria-pressed={section === item.id}
              disabled={busy}
              onClick={() => openSection(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <span className={`mode ${config?.mode ?? ""}`}>
          {config ? (config.mode === "llm" ? "LLM" : "Демо") : "…"}
        </span>
      </header>

      <main>
        <section className="heading">
          <div>
            <h1>{titles[section]}</h1>
            <FiltersBar
              report={report}
              busy={busy}
              onLine={changeLine}
              onCount={changeCount}
              onReset={() => request(START_TOOL, {}, "Сбросить фильтры", {})}
            />
          </div>
        </section>

        {error && <p className="error" role="alert">{error}</p>}

        {report ? (
          <>
            <KpiGrid kpis={report.kpis} busy={busy} onSelect={selectMetric} />
            <div className="workspace">
              <div className="analysis">
                <ChartPanel
                  report={report}
                  busy={busy}
                  onGrain={grain => request(
                    report.filters.tool,
                    { grain },
                    grain === "hour" ? "По часам" : "По сменам"
                  )}
                />
                <TablePanel report={report} />
              </div>
              <ChatPanel
                messages={messages}
                config={config}
                busy={busy}
                question={question}
                onQuestion={setQuestion}
                onAsk={submit}
                onReset={reset}
              />
            </div>
          </>
        ) : (
          <p className="loading">{busy ? "Загружаю отчёт…" : "Нет данных."}</p>
        )}

        <details className="about">
          <summary>Данные и методика</summary>
          <p>
            Учебная витрина: 42 смены по 12 часов, с 29 октября 08:00 по 19 ноября 08:00 2026 года.
            Время местное. Линия А — станки S-101 и S-102, линия Б — S-201 и S-202.
          </p>
          <dl>
            <dt>Выпуск и план</dt>
            <dd>Отклонение = (факт − план) / план × 100 %. Существенное отставание начинается с 10 %.</dd>
            <dt>Доля брака</dt>
            <dd>Брак / (годные детали + весь брак) × 100 %.</dd>
            <dt>Загрузка и простои</dt>
            <dd>
              Загрузка = рабочие машино-минуты / доступные машино-минуты × 100 %.
              Порог длительности применяется к отдельным событиям журнала.
            </dd>
            <dt>Сравнение периодов</dt>
            <dd>Берутся те же станки и часы ровно на семь суток раньше. Пропуски отмечены прочерком.</dd>
            <dt>Как считается ответ</dt>
            <dd>
              Сервер выполняет SQL-запросы к SQLite и отдаёт ряды данных.
              График строится в браузере по этим рядам.
              При подключённой модели она выбирает расчётную функцию, а текст собирается из проверенных фактов.
            </dd>
          </dl>
        </details>

        <footer>
          <span>Такт / Производственная аналитика</span>
          <span>Данные обновляются при каждом запросе</span>
        </footer>
      </main>
    </div>
  );
}
