import type { Config, Report } from "./types";

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Нет соединения с сервером.");
  }

  const data: unknown = await response.json().catch(() => null);
  if (!response.ok || data === null || typeof data !== "object") {
    const payload = data as { error?: string; detail?: string } | null;
    const message = payload?.error ?? payload?.detail;
    throw new Error(typeof message === "string" ? message : `Ошибка сервера (${response.status}).`);
  }
  return data as T;
}

export const getConfig = (signal?: AbortSignal) =>
  request<Config>("/api/config", undefined, signal);

export const ask = (question: string, context: object, signal?: AbortSignal) =>
  request<Report>("/api/chat", { question, context }, signal);

export const buildReport = (tool: string, args: object, context: object, signal?: AbortSignal) =>
  request<Report>("/api/report", { tool, arguments: args, context }, signal);
