export type Cell = string | number | boolean | null;

export interface Config {
  mode: "llm" | "demo";
  model: string;
}

export interface Filters {
  count: number;
  line: string;
  machine: string;
  shift: string;
  status: string;
  defect: string;
  since: string;
  until: string;
  offset: number;
  view: string;
  metric: string;
  compare: string;
  lag: boolean;
  top: number;
  min: number;
  threshold: number;
  grain: string;
  tool: string;
  basis: string;
}

export interface Column {
  key: string;
  label: string;
  unit: string;
}

export interface Kpis {
  good: number;
  plan: number;
  bad: number;
  rate: number | null;
  down: number;
  load: number | null;
}

export interface SeriesPoint {
  label: string;
  actual: number | null;
  plan: number | null;
  previous: number | null;
  downtime: number;
}

export interface Report {
  schema_version: string;
  tool: string;
  mode: "direct" | "demo" | "llm";
  model: string;
  filters: Filters;
  metric_label: string;
  unit: string;
  kpis: Kpis;
  table: {
    columns: Column[];
    rows: Record<string, Cell>[];
  };
  series: SeriesPoint[];
  facts: string[];
  summary: string;
  recommendations: string[];
}

export interface Message {
  role: "user" | "bot";
  text: string;
  tips?: string[];
}
