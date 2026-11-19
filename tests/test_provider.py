"""Exercise the real OpenAI SDK over loopback and the real analytics SQLite database."""
import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from analytics import init_db
from llm import ProviderError, run_chat


def completion(message, reason):
    return 200, {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "message": message, "finish_reason": reason}],
    }


def tool_call(name, arguments):
    return completion({
        "role": "assistant",
        "tool_calls": [{
            "id": "call-1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }],
    }, "tool_calls")


def narrative(*fact_ids):
    content = {"summary_facts": list(fact_ids), "recommendations": ["R1"]}
    return completion({"role": "assistant", "content": json.dumps(content)}, "stop")


@contextmanager
def local_provider(*replies):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            index = len(requests)
            requests.append((self.path, request))
            if self.path == "/v1/chat/completions" and index < len(replies):
                status, body = replies[index]
            else:
                status, body = 400, {"error": {"message": "Unexpected request"}}
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.03})
        worker.start()
        try:
            settings = {
                "LLM_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                "LLM_API_KEY": "local-test-key",
                "LLM_MODEL": "test-model",
                "NO_PROXY": "127.0.0.1",
                "no_proxy": "127.0.0.1",
            }
            with patch.dict(os.environ, settings):
                yield requests
        finally:
            server.shutdown()
            worker.join()


class ProviderProtocolTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Path(directory.name) / "workshop.sqlite"
        init_db(self.db)

    def test_shortfalls_and_structured_report(self):
        question = "Где выпуск отстаёт от плана за последние 5 смен?"
        with local_provider(tool_call("plan_shortfalls", {"count": 5}), narrative("F1", "F2")) as requests:
            result = run_chat(self.db, question, {})
        self.assertEqual([path for path, _ in requests], ["/v1/chat/completions"] * 2)
        plan, final = [request for _, request in requests]
        self.assertIn("plan_shortfalls", [tool["function"]["name"] for tool in plan["tools"]])
        self.assertEqual(plan["tool_choice"], "required")
        self.assertEqual(json.loads(plan["messages"][-1]["content"])["question"], question)
        self.assertEqual(final["tools"], plan["tools"])
        self.assertEqual(final["tool_choice"], "none")
        self.assertNotIn("provider", final)  # OpenRouter routing options are vendor-specific.
        tool_message = final["messages"][-1]
        self.assertEqual(tool_message["role"], "tool")
        self.assertEqual(tool_message["tool_call_id"], final["messages"][-2]["tool_calls"][0]["id"])
        computed = json.loads(tool_message["content"])
        schema = final["response_format"]
        self.assertEqual(schema["type"], "json_schema")
        self.assertIs(schema["json_schema"]["strict"], True)
        properties = schema["json_schema"]["schema"]["properties"]
        self.assertEqual(properties["summary_facts"]["items"]["enum"], list(computed["facts"]))
        self.assertEqual(result["mode"], "llm")
        self.assertEqual(result["model"], "test-model")
        self.assertEqual(result["summary"], " ".join(computed["facts"].values()))
        self.assertEqual(result["recommendations"], [computed["recommendations"]["R1"]])
        rows = result["table"]["rows"]
        projected = [(r["shift_id"], r["line"], r["good"], r["plan"], r["bad"], r["down"]) for r in rows]
        self.assertEqual(projected, [
            ("17.11 · день", "А", 469, 720, 87, 267),
            ("18.11 · день", "Б", 552, 720, 103, 88),
        ])
        for row in rows:
            self.assertAlmostEqual(row["rate"], 100 * row["bad"] / (row["bad"] + row["good"]))
            self.assertAlmostEqual(row["deviation"], 100 * (row["good"] - row["plan"]) / row["plan"])

    def test_machine_ranking_and_filter_context(self):
        with local_provider(tool_call("machine_ranking", {"top": 3, "metric": "quality"}),
                            narrative("F1")) as requests:
            result = run_chat(self.db, "Топ-3 станка по доле брака", {"count": 5})
        planner_input = json.loads(requests[0][1]["messages"][-1]["content"])
        self.assertEqual(planner_input["context"]["count"], 5)
        rows = result["table"]["rows"]
        self.assertEqual([(r["machine"], r["bad"], r["good"]) for r in rows], [
            ("S-102", 108, 1687), ("S-201", 121, 1954), ("S-202", 90, 1530),
        ])

    def test_fabricated_fact_is_rejected(self):
        with local_provider(tool_call("shift_summary", {}), narrative("F999")):
            with self.assertRaisesRegex(ProviderError, "неизвестный результат"):
                run_chat(self.db, "Выпуск по сменам")

    def test_provider_error_is_reported(self):
        with local_provider((401, {"error": {"message": "Invalid credentials"}})) as requests:
            with self.assertRaisesRegex(ProviderError, "HTTP 401"):
                run_chat(self.db, "Отчёт по сменам")
        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()
