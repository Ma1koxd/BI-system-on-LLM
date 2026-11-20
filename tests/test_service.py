import base64
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import analytics
from app import build_app


class ServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        env = patch.dict(os.environ, {k: "" for k in (
            "LLM_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_BASE_URL", "LLM_BASE_URL")})
        env.start()
        self.addCleanup(env.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "data.sqlite3"
        app = build_app(self.db)
        await self.enterAsyncContext(app.router.lifespan_context(app))
        self.http = await self.enterAsyncContext(AsyncClient(transport=ASGITransport(app=app),
                                                             base_url="http://test"))

    async def ask(self, question, context=None):
        r = await self.http.post("/api/chat", json={"question": question, "context": context or {}})
        self.assertEqual(r.status_code, 200, r.text[:250])
        return r.json()

    async def test_all_tools_produce_consistent_json_tables_and_png(self):
        for spec in analytics.TOOLS:
            name = spec["function"]["name"]
            with self.subTest(name=name):
                r = await self.http.post("/api/report", json={"tool": name})
                self.assertEqual(r.status_code, 200, r.text[:250])
                result = r.json()
                self.assertEqual(result["schema_version"], "1.0")
                self.assertEqual(result["tool"], name)
                self.assertEqual(result["chart"]["mime_type"], "image/png")
                self.assertTrue(base64.b64decode(result["chart"]["data"], validate=True).startswith(b"\x89PNG\r\n\x1a\n"))
                keys = {c["key"] for c in result["table"]["columns"]}
                self.assertTrue(result["table"]["rows"])
                self.assertTrue(all(set(row) == keys for row in result["table"]["rows"]))
        self.assertEqual((await self.http.get("/")).status_code, 200)
        self.assertEqual((await self.http.get("/api/config")).json(), {"mode": "demo", "model": ""})

    async def test_context_empty_selection_and_reset(self):
        lag = await self.ask("Где выпуск сильно отстаёт от плана и какой там процент брака за последние 5 смен?")
        self.assertEqual([(r["good"], r["plan"]) for r in lag["table"]["rows"]], [(469, 720), (552, 720)])
        night = await self.ask("Покажи только ночные смены", lag["filters"])
        self.assertEqual(night["table"]["rows"], [])
        full = await self.ask("Сбросить фильтры", night["filters"])
        self.assertEqual(full["kpis"]["good"], 6658)
        weekly = await self.ask("Сравни с прошлой неделей", full["filters"])
        self.assertTrue(all(r["previous"] is not None for r in weekly["table"]["rows"]))
        window = await self.ask("Сравни с прошлой неделей за 42 смены")
        self.assertTrue(any(r["previous"] is None for r in window["table"]["rows"]))

    async def test_threshold_hourly_delta_and_event_reason(self):
        out = await self.ask("Покажи отставание от плана более 25,5 %")
        self.assertEqual(len(out["table"]["rows"]), 1)
        events = await self.ask("Покажи простои длиннее 30 минут с причиной")
        rows = events["table"]["rows"]
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(r["down"] > 30 and r["reason"] for r in rows))
        out = await self.ask("Выпуск по часам на линии А за 17.11.2026")
        rows = out["table"]["rows"]
        self.assertEqual(len(rows), 24)
        self.assertIsNone(rows[0]["hour_change"])
        self.assertEqual(rows[1]["hour_change"], rows[1]["good"] - rows[0]["good"])

    async def test_invalid_inputs_and_reopen(self):
        analytics.init_db(self.db)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM production").fetchone()[0], 2016)
        conn.close()
        for request in ({"tool": "execute_sql"}, {"tool": "shift_summary", "arguments": {"machine": "S-999"}},
                        {"tool": "shift_summary", "arguments": {"since": "2026-02-30"}},
                        {"tool": "plan_shortfalls", "arguments": {"threshold": "25"}}):
            response = await self.http.post("/api/report", json=request)
            self.assertEqual(response.status_code, 422)
            self.assertIn("error", response.json())


if __name__ == "__main__":
    unittest.main()
