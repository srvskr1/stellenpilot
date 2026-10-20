"""Local LLM support, tested against a fake server that speaks the Ollama and OpenAI APIs."""
import json
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from stellenpilot.config import Settings
from stellenpilot.llm import LLM, parse_json

SEEN = []


class Fake(BaseHTTPRequestHandler):
    reject_json_mode = False

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            return self._send(200, {"models": [{"name": "qwen2.5:7b"}]})
        if self.path == "/v1/models":
            return self._send(200, {"data": [{"id": "local-model"}]})
        self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append((self.path, body))
        if self.path == "/api/chat":
            return self._send(200, {"message": {"content": '{"match": 77}'}})
        if self.path == "/v1/chat/completions":
            if "response_format" in body and Fake.reject_json_mode:
                return self._send(400, {"error": "response_format not supported"})
            return self._send(200, {"choices": [{"message": {"content": 'Sure! ```json\n{"match": 66, "why": "a \\"quoted\\" word"}\n```'}}]})
        self._send(404, {})


def settings_for(home: Path, **llm):
    (home / "config.toml").write_text("[llm]\n" + "\n".join(f'{k} = {json.dumps(v)}' for k, v in llm.items()), encoding="utf-8")
    return Settings(home)


class LocalLLMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from helpers import Server
        cls.srv = Server(Fake)
        cls.base = cls.srv.base

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def setUp(self):
        SEEN.clear()
        Fake.reject_json_mode = False
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ollama_native_api_sets_context_and_json(self):
        llm = LLM(settings_for(self.home, provider="ollama", model="qwen2.5:7b", base_url=self.base, num_ctx=16384))
        self.assertEqual(llm.complete_json("sys", "user")["match"], 77)
        path, body = SEEN[-1]
        self.assertEqual(path, "/api/chat")
        self.assertEqual(body["format"], "json")
        self.assertEqual(body["options"]["num_ctx"], 16384)
        self.assertIn("qwen2.5:7b", llm.list_models())

    def test_openai_compatible_server_and_fenced_json(self):
        llm = LLM(settings_for(self.home, provider="llamacpp", model="local-model", base_url=self.base + "/v1"))
        out = llm.complete_json("sys", "user")
        self.assertEqual(out["match"], 66)
        self.assertEqual(out["why"], 'a "quoted" word')
        self.assertEqual(SEEN[-1][1]["response_format"], {"type": "json_object"})
        self.assertEqual(llm.list_models(), ["local-model"])

    def test_server_without_json_mode_falls_back(self):
        Fake.reject_json_mode = True
        llm = LLM(settings_for(self.home, provider="lmstudio", model="local-model", base_url=self.base + "/v1"))
        self.assertEqual(llm.complete_json("sys", "user")["match"], 66)
        self.assertNotIn("response_format", SEEN[-1][1])
        self.assertFalse(llm.json_mode)

    def test_local_defaults(self):
        llm = LLM(settings_for(self.home, provider="ollama", model="qwen2.5:7b"))
        self.assertEqual(llm.base_url, "http://localhost:11434")
        self.assertEqual(llm.timeout, 600)
        self.assertEqual(llm.max_chars, 4000)

    def test_bad_settings_are_explained(self):
        with self.assertRaises(RuntimeError):
            LLM(settings_for(self.home, provider="local", model="x"))      # no base_url
        with self.assertRaises(RuntimeError):
            LLM(settings_for(self.home, provider="ollama"))                # no model
        with self.assertRaises(RuntimeError):
            LLM(settings_for(self.home, provider="gpt5000", model="x"))    # unknown provider


class FallbackTests(unittest.TestCase):
    def test_broken_model_falls_back_to_keyword_score(self):
        import tomllib
        from importlib import resources
        from unittest import mock
        from stellenpilot.score import score_job
        profile = tomllib.loads(resources.files("stellenpilot").joinpath("examples/profile.example.toml").read_text(encoding="utf-8"))
        broken = mock.Mock(enabled=True, max_chars=4000)
        broken.complete_json.side_effect = ValueError("LLM did not return JSON")
        job = {"title": "Working Student Data", "company": "X", "location": "Essen", "description": "Python and SQL."}
        r = score_job(job, profile, broken)
        self.assertIsInstance(r["match"], int)
        self.assertIn("keyword score used", r["why"])

    def test_match_given_as_text_is_still_read(self):
        from unittest import mock
        from stellenpilot.score import llm_score
        job = {"title": "Working Student Data", "company": "X", "location": "Essen", "description": "Python and SQL."}
        for given, want in (("85%", 85), ("72.6", 73), ("64/100", 64), (91, 91), (None, 0), ("high", 0), ("250", 100)):
            llm = mock.Mock(max_chars=4000)
            llm.complete_json.return_value = {"match": given}
            with self.subTest(given=given):
                self.assertEqual(llm_score(llm, job, {})["match"], want)


class ParseJsonTests(unittest.TestCase):
    def test_tolerates_chatter_and_nested_braces(self):
        self.assertEqual(parse_json('Here: {"a": {"b": "}"}, "c": 1} thanks')["c"], 1)

    def test_rejects_non_json(self):
        with self.assertRaises(ValueError):
            parse_json("no json here")


if __name__ == "__main__":
    unittest.main()


class ThinkingTest(unittest.TestCase):
    def test_strip_thinking(self):
        from stellenpilot.llm import parse_json, strip_thinking
        self.assertEqual(strip_thinking('<think>long reasoning {"x": 1}</think>\n{"match": 80}'), '{"match": 80}')
        self.assertEqual(parse_json(strip_thinking('<think>{"bad": 1}</think>{"good": 2}')), {"good": 2})
        self.assertEqual(strip_thinking("plain"), "plain")

    def test_ollama_sends_think_false_and_falls_back(self):
        from unittest import mock
        from stellenpilot import llm as L
        from stellenpilot.http import HttpError

        class S:
            cfg = {"llm": {"provider": "ollama", "model": "qwen3.5:4b", "base_url": ""}}
            def __getitem__(self, k): return self.cfg[k]
            @staticmethod
            def secret(n): return None
        bodies = []

        def fake(url, body=None, **kw):
            bodies.append(dict(body))
            if "think" in body:
                raise HttpError(400, '{"error":"model does not support thinking (think)"}')
            return {"message": {"content": '{"ok": true}'}}
        m = L.LLM(S())
        with mock.patch.object(L, "request_json", side_effect=fake):
            self.assertEqual(m.complete_json("s", "u"), {"ok": True})
            m.complete("s", "u")
        self.assertIs(bodies[0]["think"], False)
        self.assertNotIn("think", bodies[1])
        self.assertNotIn("think", bodies[2])  # remembered for later calls
