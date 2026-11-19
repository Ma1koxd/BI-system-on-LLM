'use strict';
const $=id=>document.getElementById(id);
const paths={
  factory:'<path d="M3 21V9l6 3V8l6 4V4h4l2 17zM7 16h1m4 0h1m4 0h1"/>',
  layers:'<path d="m3 8 9-5 9 5-9 5zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v5m10-5v5M3 11h18"/>',
  output:'<path d="m3.5 7.5 8.5-5 8.5 5v9L12 22l-8.5-5.5zM4 7.5l8 5 8-5M12 12.5V22M8 5l8 5"/>',
  quality:'<path d="M12 2.5 20 6v6c0 4-3.5 7-8 9.5C7.5 19 4 16 4 12V6zM12 8v5m0 3h.01"/>',
  down:'<circle cx="12" cy="12" r="9"/><path d="M12 6.5v6l4 2"/>',
  load:'<path d="M3 18a10 10 0 0 1 18 0M12 16l5-7M5 13l2 1m4-6v2"/><circle cx="12" cy="16" r="2"/>',
  spark:'<path d="m10 3 2.2 6.8L19 12l-6.8 2.2L10 21l-2.2-6.8L1 12l6.8-2.2zM19 2l.9 2.2L22 5l-2.1.8L19 8l-.8-2.2L16 5l2.2-.8z"/>',
  reset:'<path d="M3 10a9 9 0 1 1 1 7M3 4v6h6"/>',send:'<path d="m3 4 18 8-18 8 3-8zM6 12h15"/>',
  user:'<circle cx="12" cy="8" r="3"/><path d="M5 20a7 7 0 0 1 14 0"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>'};
const icon=k=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths[k]+'</svg>';
document.querySelectorAll('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));

const numberFormat = new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 1});
const pageSize = 6;
const metrics = {
  output: {name: 'Выпуск продукции', key: 'good', unit: 'шт.', color: '#cc6937', bg: '#fbecdf'},
  quality: {name: 'Доля брака', key: 'rate', unit: '%', color: '#a55b55', bg: '#f8e9e5'},
  down: {name: 'Простои', key: 'down', unit: 'мин', color: '#9d772f', bg: '#f7efdc'},
  load: {name: 'Загрузка станков', key: 'load', unit: '%', color: '#477863', bg: '#e6eee6'}
};
const tableTitles = {
  plan_shortfalls: 'Смены с отставанием',
  hourly_output: 'Динамика по часам',
  machine_ranking: 'Рейтинг станков',
  downtime_events: 'Журнал простоев',
  defect_breakdown: 'Брак по причинам',
  compare_week: 'Сравнение с прошлой неделей'
};
let report = null;
let requestController = null;
let config = null;
let tablePage = 0;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text).replace(/[\u2013\u2014]/g, '-');
  return node;
}

function number(value) {
  return typeof value === 'number' && Number.isFinite(value) ? numberFormat.format(value) : '-';
}

function addMessage(who, text, tips = []) {
  const article = element('article', 'msg ' + who);
  const meta = element('div', 'msg-meta');
  const symbol = element('span', who === 'user' ? 'person-icon' : 'boticon');
  symbol.innerHTML = icon(who === 'user' ? 'user' : 'spark');
  if (who === 'user') meta.append('Вы ', symbol);
  else meta.append(symbol, ' Такт');
  article.append(meta, element('div', 'msg-text', text));
  if (tips.length) {
    const note = element('div', 'takeaway');
    note.append(element('strong', '', tips.length === 1 ? 'Рекомендация' : 'Рекомендации'));
    for (const tip of tips) note.append(element('p', '', tip));
    article.append(note);
  }
  const log = $('conversation');
  log.append(article);
  log.scrollTop = log.scrollHeight;
}

function renderKpis() {
  const kpis = report.kpis;
  const notes = {
    output: 'План ' + number(kpis.plan) + ' шт.',
    quality: number(kpis.bad) + ' шт. брака',
    down: 'Суммарно по станкам',
    load: 'По машино-часам'
  };
  const cards = Object.entries(metrics).map(([key, metric]) => {
    const button = element('button', 'kpi');
    button.dataset.k = key;
    button.setAttribute('aria-label', 'Показать показатель «' + metric.name + '»');
    const head = element('span', 'kpi-head');
    const glyph = element('span', 'tileicon');
    glyph.style.color = metric.color;
    glyph.style.background = metric.bg;
    glyph.innerHTML = icon(key);
    head.append(glyph, metric.name);
    const value = element('div', 'k-value', number(kpis[metric.key]));
    value.append(element('small', '', metric.unit));
    button.append(head, value, element('div', 'k-foot', notes[key]));
    return button;
  });
  $('kpis').replaceChildren(...cards);
}

function displayFilters() {
  const f = report.filters;
  $('line').value = f.line;
  const count = $('count');
  const dates = f.since || f.until;
  const selected = dates ? 'dates' : String(f.count);
  count.querySelectorAll('[data-custom]').forEach(option => option.remove());
  if (![...count.options].some(option => option.value === selected)) {
    const opt = new Option(dates ? 'Выбранные даты' : f.count + ' смен', selected);
    opt.dataset.custom = 'true';
    count.add(opt);
  }
  count.value = selected;
  const period = dates
    ? [f.since || 'Начало витрины', f.until || 'Конец витрины'].join(' - ')
    : 'Завершённые смены: ' + f.count;
  $('period').textContent = period + ' · ' + (f.line === 'Все' ? 'Линии А и Б' : 'Линия ' + f.line);
  const flags = [
    f.shift !== 'Все' && f.shift,
    f.machine !== 'Все' && f.machine,
    f.status !== 'Все' && 'Заказ · ' + f.status,
    f.defect !== 'Все' && 'Дефект · ' + f.defect,
    f.lag && 'Отставание ≥ ' + number(f.threshold) + ' %',
    f.top > 0 && 'Топ-' + f.top,
    f.compare === 'week' && 'Сравнение с прошлой неделей',
    f.offset > 0 && 'Неделей ранее',
    f.tool === 'downtime_events' && f.min > 0 && 'Простой > ' + f.min + ' мин'
  ].filter(Boolean);
  const context = $('context');
  context.replaceChildren(...flags.map(flag => element('span', '', flag)));
  if (flags.length) {
    const clear = element('button', '', 'Сбросить фильтры');
    clear.onclick = () => requestReport('shift_summary', {}, 'Сбросить фильтры', {});
    context.append(clear);
  }
  const section = f.tool === 'downtime_events' || f.view === 'events'
    ? 'events' : f.view === 'machine' || f.tool === 'machine_ranking' ? 'machine' : 'shift';
  document.querySelectorAll('[data-nav]').forEach(button => {
    const active = button.dataset.nav === section;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  $('pageTitle').textContent = {shift:'Производственная сводка', machine:'Анализ оборудования', events:'Анализ простоев'}[section];
}

function renderChart() {
  const f = report.filters;
  const byHour = f.grain === 'hour';
  const granularity = byHour ? 'по часам' : 'по сменам';
  $('chartTitle').textContent = report.metric_label;
  $('shiftChart').setAttribute('aria-pressed', String(!byHour));
  $('hourChart').setAttribute('aria-pressed', String(byHour));
  const chart = $('chart');
  if (!report.series.length) {
    chart.replaceChildren(element('div', 'empty', 'Нет точек для выбранной выборки'));
  } else {
    const image = element('img', 'report-plot');
    image.alt = report.chart.alt || report.metric_label + ' ' + granularity;
    image.src = 'data:image/png;base64,' + report.chart.data;
    chart.replaceChildren(image);
  }
  $('chartNote').textContent = f.compare === 'week'
    ? 'Сравнение с теми же часами и оборудованием семь суток назад.'
    : report.metric_label + ' ' + granularity + ', ' + report.unit + '.';
}

function renderTable() {
  const {rows, columns} = report.table;
  const f = report.filters;
  $('tableTitle').textContent = tableTitles[f.tool] || ({machine:'Показатели по станкам', line:'Показатели по линиям', shift:'Показатели по сменам'})[f.view] || 'Результаты анализа';
  $('rowCount').textContent = 'Строк: ' + rows.length;
  const table = $('table');
  table.replaceChildren();
  const head = element('thead');
  const header = element('tr');
  head.append(header);
  table.append(head);
  for (const column of columns) {
    const cell = element('th', '', column.label + (column.unit ? ', ' + column.unit : ''));
    cell.scope = 'col';
    header.append(cell);
  }
  const body = element('tbody');
  table.append(body);
  const start = tablePage * pageSize;
  for (const row of rows.slice(start, start + pageSize)) {
    const tr = element('tr');
    body.append(tr);
    for (const {key} of columns) {
      const value = row[key];
      const cell = element('td');
      tr.append(cell);
      const display = typeof value === 'number' ? number(value) : value ?? '-';
      if (key === 'deviation' && typeof value === 'number') {
        cell.append(element('span', value <= -10 ? 'bad' : value >= 0 ? 'ok' : '', display));
      } else {
        cell.textContent = display;
      }
    }
  }
  if (!rows.length) {
    const tr = element('tr');
    const cell = element('td');
    tr.append(cell);
    body.append(tr);
    cell.colSpan = Math.max(1, columns.length);
    cell.className = 'empty';
    cell.textContent = 'Нет подходящих записей';
  }
  const pager = $('pager');
  pager.replaceChildren();
  if (rows.length > pageSize) {
    const end = Math.min(start + pageSize, rows.length);
    const previous = element('button', '', 'Назад');
    const next = element('button', '', 'Далее');
    previous.disabled = tablePage === 0;
    next.disabled = end === rows.length;
    previous.onclick = () => { tablePage--; renderTable() };
    next.onclick = () => { tablePage++; renderTable() };
    const group = element('div');
    group.append(previous, ' ', next);
    pager.append(element('span', '', (start + 1) + '-' + end + ' из ' + rows.length), group);
  }
  $('exportJson').disabled = false;
}

function render() {
  tablePage = 0;
  displayFilters();
  renderKpis();
  renderChart();
  renderTable();
}

function setBusy(busy) {
  const selector = '[data-nav], [data-prompt], .kpi, #count, #line, #context button, .segments button, #send';
  document.querySelectorAll(selector).forEach(button => { button.disabled = busy });
  $('overview').setAttribute('aria-busy', String(busy));
  const mode = config?.mode;
  const name = report?.mode === 'llm' ? report.model : config?.model;
  $('mode').textContent = busy ? 'Обрабатываю запрос…' : mode === 'llm'
    ? 'LLM · ' + (name || 'Подключена') : mode === 'demo' ? 'Демонстрационный режим' : 'Нет подключения';
}

async function api(path, body, signal) {
  let response;
  try {
    response = await fetch(path, {
      method: body ? 'POST' : 'GET',
      headers: body ? {'Content-Type':'application/json'} : {},
      body: body ? JSON.stringify(body) : undefined,
      signal
    });
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw Error('Нет соединения с Python-сервером. Проверьте, что сервис запущен, и повторите запрос.');
  }
  const json = await response.json().catch(() => null);
  if (!response.ok || !json || typeof json !== 'object') {
    const detail = json?.error || json?.detail;
    throw Error(typeof detail === 'string' ? detail : 'Сервер не вернул отчёт (HTTP ' + response.status + ').');
  }
  return json;
}

function validateReport(result) {
  if (!result.filters || !result.kpis || !Array.isArray(result.table?.columns)
      || !Array.isArray(result.table?.rows) || !Array.isArray(result.series)
      || typeof result.summary !== 'string' || !Array.isArray(result.recommendations)) {
    throw Error('Сервер вернул неполный отчёт.');
  }
  if (result.series.length && (result.chart?.mime_type !== 'image/png' || typeof result.chart.data !== 'string' || !result.chart.data)) {
    throw Error('Сервер не вернул график Matplotlib.');
  }
}

async function update(path, body, text, reset = false) {
  requestController?.abort();
  const controller = new AbortController();
  requestController = controller;
  if (reset) $('conversation').replaceChildren();
  $('failure').hidden = true;
  $('failure').textContent = '';
  addMessage('user', text);
  setBusy(true);
  try {
    if (!config) config = await api('/api/config', null, controller.signal);
    const result = await api(path, body, controller.signal);
    if (requestController !== controller) return;
    validateReport(result);
    report = result;
    render();
    addMessage('bot', report.summary, report.recommendations);
  } catch (err) {
    if (controller.signal.aborted || requestController !== controller) return;
    if (report) displayFilters();
    $('failure').textContent = err.message;
    $('failure').hidden = false;
    addMessage('bot', err.message);
  } finally {
    if (requestController === controller) {
      requestController = null;
      setBusy(false);
    }
  }
}

function requestReport(tool, args, text, context = report?.filters || {}) {
  return update('/api/report', {tool, arguments:args, context}, text);
}

function resetReport() {
  $('question').value = '';
  return update('/api/report', {tool:'shift_summary', arguments:{}, context:{}},
    'Как цех выполнил план за последние 5 смен?', true);
}

function ask(question) {
  const text = question.trim().replace(/[\u2013\u2014]/g, '-');
  if (!text || requestController) return;
  $('question').value = '';
  return update('/api/chat', {question:text, context:report?.filters || {}}, text);
}

function bindEvents() {
  $('ask').onsubmit = event => { event.preventDefault(); ask($('question').value) };
  $('question').onkeydown = event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      ask(event.target.value);
    }
  };
  document.querySelectorAll('[data-prompt]').forEach(button => {
    button.onclick = () => ask(button.dataset.prompt);
  });
  $('kpis').onclick = event => {
    const key = event.target.closest('[data-k]')?.dataset.k;
    if (!key || !report) return;
    const f = report.filters;
    const view = ['shift','line','machine'].includes(f.view) ? f.view : 'shift';
    const tool = key === 'down' ? 'downtime_events' : key === 'load' ? 'equipment_load' : 'shift_summary';
    requestReport(tool, {metric:key, view:key === 'down' ? 'events' : view, top:0, lag:false}, metrics[key].name);
  };
  document.querySelectorAll('[data-nav]').forEach(button => {
    button.onclick = () => {
      const view = button.dataset.nav;
      const events = view === 'events';
      requestReport(events ? 'downtime_events' : 'shift_summary',
        {view, metric:events ? 'down' : 'output', lag:false, top:0, min:0}, button.textContent);
    };
  });
  $('line').onchange = event => requestReport(report?.filters.tool || 'shift_summary',
    {line:event.target.value, machine:'Все'}, event.target.selectedOptions[0].text);
  $('count').onchange = event => requestReport(report?.filters.tool || 'shift_summary',
    {count:Number(event.target.value), since:'', until:'', offset:0}, event.target.selectedOptions[0].text);
  for (const [id, grain] of [['shiftChart','shift'],['hourChart','hour']]) {
    $(id).onclick = () => requestReport(report?.filters.tool || 'shift_summary', {grain}, $(id).textContent);
  }
  $('exportJson').onclick = () => {
    if (!report) return;
    const file = new Blob([JSON.stringify(report.table, null, 2)], {type:'application/json;charset=utf-8'});
    const href = URL.createObjectURL(file);
    const link = element('a');
    link.href = href;
    link.download = 'takt-' + report.filters.tool + '.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  };
  $('reset').onclick = resetReport;
  $('brand').onclick = event => { event.preventDefault(); resetReport() };
  $('method').onclick = $('help').onclick = () => $('about').showModal();
  $('close').onclick = () => $('about').close();
}

if (location.protocol === 'file:') {
  location.replace('offline.html');
} else {
  bindEvents();
  resetReport();
}
