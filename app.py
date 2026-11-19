"""Такт HTTP API. Run with: python -m uvicorn app:app --port 8765."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

import analytics
import llm
from charts import chart_for
from demo import parse_question


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
Cell = str | int | float | bool | None


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    context: dict[str, Cell] = Field(default_factory=dict, max_length=24)


class ChatRequest(RequestBody):
    question: str = Field(min_length=1, max_length=1500)


class ToolRequest(RequestBody):
    tool: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Cell] = Field(default_factory=dict, max_length=24)


class Column(BaseModel):
    key: str
    label: str
    unit: str


class Table(BaseModel):
    columns: list[Column]
    rows: list[dict[str, Cell]]

    @model_validator(mode="after")
    def check_columns(self):
        keys = {c.key for c in self.columns}
        if len(keys) != len(self.columns) or any(row.keys() != keys for row in self.rows):
            raise ValueError("Структура строк и столбцов таблицы расходится.")
        return self


class KPI(BaseModel):
    good: int
    plan: int
    bad: int
    rate: float | None
    down: int
    load: float | None


class Point(BaseModel):
    model_config = ConfigDict(extra="allow")
    label: str
    actual: float | None
    plan: float | None
    previous: float | None
    downtime: int


class Chart(BaseModel):
    mime_type: Literal["image/png"]
    data: str = Field(description="Изображение Matplotlib, закодированное в base64")
    alt: str


class Report(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    tool: str
    mode: Literal["direct", "demo", "llm"]
    model: str
    filters: dict[str, Cell]
    metric_label: str
    unit: str
    kpis: KPI
    table: Table
    series: list[Point]
    chart: Chart
    facts: list[str]
    summary: str
    recommendations: list[str]


def direct_report(db, tool, arguments, context, mode):
    report = analytics.execute_tool(db, tool, arguments, context)
    return {**report, "summary": " ".join(report["facts"]),
            "recommendations": [report["recommendation"]], "mode": mode, "model": ""}


def build_app(db_path=None):
    db = Path(db_path or os.getenv("DATABASE_PATH", ROOT / "data" / "workshop.sqlite3"))

    @asynccontextmanager
    async def lifespan(app):
        db.parent.mkdir(parents=True, exist_ok=True)
        analytics.init_db(db)
        yield

    app = FastAPI(title="Такт BI", version="2.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def malformed(request: Request, error: RequestValidationError):
        first = error.errors()[0]
        field = ".".join(map(str, first["loc"][1:])) or "body"
        return JSONResponse({"error": f"Проверьте поле {field} в JSON-запросе."}, status_code=422)

    @app.exception_handler(llm.ProviderError)
    async def unavailable(request: Request, error: llm.ProviderError):
        status = 503 if isinstance(error, llm.ProviderConfigurationError) else 502
        return JSONResponse({"error": str(error)}, status_code=status)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, error: ValueError):
        return JSONResponse({"error": str(error)}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        settings = llm.get_config()
        return {"mode": "llm" if settings["configured"] else "demo",
                "model": settings["model"] if settings["configured"] else ""}

    def finish(report):
        return {**report, "tool": report["filters"]["tool"], "chart": chart_for(report)}

    @app.post("/api/report", response_model=Report)
    def manual(body: ToolRequest):
        return finish(direct_report(db, body.tool, body.arguments, body.context, "direct"))

    @app.post("/api/chat", response_model=Report)
    def chat(body: ChatRequest):
        question = body.question.strip()
        if not question:
            raise ValueError("Введите вопрос.")
        context = analytics.validate_filters(body.context)
        if llm.get_config()["configured"]:
            report = llm.run_chat(db, question, context)
        else:
            tool, arguments = parse_question(question, context)
            report = direct_report(db, tool, arguments, context, "demo")
        return finish(report)

    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="dashboard")
    return app


app = build_app()
