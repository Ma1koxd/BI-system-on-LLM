import type { Cell } from "./types";

const formatter = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

export function formatNumber(value: Cell): string {
  if (typeof value === "number" && Number.isFinite(value)) return formatter.format(value);
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}
