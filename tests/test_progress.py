"""Live progress for slow AI work: the table, streaming from local model servers, and the endpoint."""
import json
import tempfile
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from unittest import mock

from stellenpilot import progress
from stellenpilot.config import Settings
from stellenpilot.llm import LLM

ANSWER = '{"skills": {"Languages": ["Python"]}, "experience": [], "projects": [], "education": []}'


class TableTests(unittest.TestCase):
    def test_stages_writing_and_end(self):
        with progress.track("t1", "Reading your CV"):
            progress.stage("Reading", expect=100)
            progress.writing('{"skills": {}, "experience": [')
            snap = progress.snapshot("t1")
            self.assertTrue(snap["active"])
            self.assertEqual(snap["chars"], 30)
            self.assertEqual(snap["found"], ["skills", "jobs"])
            self.assertEqual(snap["percent"], 30)
        self.assertFalse(progress.snapshot("t1")["active"])
        self.assertEqual(progress.snapshot("unknown"), {"active": False})

    def test_percent_never_claims_done_while_running(self):
        with progress.track("t2"):
            progress.stage("Writing", expect=10)
            progress.writing("x" * 50)  # longer than expected
            self.assertEqual(progress.snapshot("t2")["percent"], 97)

    def test_second_start_is_refused(self):
        with progress.track("t3"):
            with self.assertRaises(progress.Busy):
                with progress.track("t3"):
                    pass
        with progress.track("t3"):  # free again afterwards
            pass

    def test_error_is_kept(self):
        with self.assertRaises(ValueError):
            with progress.track("t4"):
                raise ValueError("model went away")
        self.assertIn("model went away", progress.snapshot("t4")["error"])

    def test_aside_returns_to_the_running_step(self):
        with progress.track("t5"):
            progress.stage("Reading your CV", expect=500)
            with progress.aside("Starting the built-in AI"):
                self.assertEqual(progress.snapshot("t5")["stage"], "Starting the built-in AI")
            snap = progress.snapshot("t5")
            self.assertEqual((snap["stage"], snap["expect"]), ("Reading your CV", 500))

    def test_no_task_means_no_reporting(self):
        progress.stage("ignored")
        progress.writing("ignored")  # nothing tracked on this thread: no error, no state


class _Fake(BaseHTTPRequestHandler):
    """Streams ANSWER in small pieces like llama.cpp (SSE) or Ollama (NDJSON)."""
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Fake.seen.append(body)
        pieces = [ANSWER[i:i + 7] for i in range(0, len(ANSWER), 7)]
        self.send_response(200)
        self.end_headers()
        if not body.get("stream"):
            out = ({"message": {"content": ANSWER}} if self.path == "/api/chat"
                   else {"choices": [{"message": {"content": ANSWER}}]})
            self.wfile.write(json.dumps(out).encode())
            return
        for p in pieces:
            if self.path == "/api/chat":
                self.wfile.write((json.dumps({"message": {"content": p}, "done": False}) + "\n").encode())
            else:
                self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}\n\n".encode())
            self.wfile.flush()
        if self.path == "/api/chat":
            self.wfile.write((json.dumps({"message": {"content": ""}, "done": True}) + "\n").encode())
        else:
            self.wfile.write(b"data: [DONE]\n\n")


class StreamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from helpers import Server
        cls.srv = Server(_Fake)
        cls.base = cls.srv.base

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def _llm(self, provider, base_url):
        with tempfile.TemporaryDirectory() as d:
            s = Settings(Path(d))
        s.cfg = {**s.cfg, "llm": {"provider": provider, "model": "m", "base_url": base_url}}
        return LLM(s)

    def _check(self, provider, base_url):
        llm = self._llm(provider, base_url)
        _Fake.seen.clear()
        with progress.track("s-" + provider):
            progress.stage("Writing", expect=len(ANSWER))
            self.assertEqual(llm.complete_json("sys", "user")["skills"], {"Languages": ["Python"]})
            snap = progress.snapshot("s-" + provider)
        self.assertTrue(_Fake.seen[0]["stream"])
        self.assertEqual(snap["chars"], len(ANSWER))
        self.assertIn("jobs", snap["found"])
        # Without anyone watching, the plain request is used as before.
        _Fake.seen.clear()
        llm.complete_json("sys", "user")
        self.assertNotIn("stream", {k for k, v in _Fake.seen[0].items() if v})

    def test_openai_compatible_server_streams(self):
        self._check("llamacpp", self.base + "/v1")

    def test_ollama_streams(self):
        self._check("ollama", self.base)


class EndpointTests(unittest.TestCase):
    def test_progress_endpoint_and_busy_reread(self):
        from stellenpilot.server import make_handler
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            home = Path(d)
            (home / "config.toml").write_text('[llm]\nprovider = "ollama"\nmodel = "m"\n', encoding="utf-8")
            (home / "cv_source.txt").write_text("Sourav Sarker\nPython SQL\n" * 5, encoding="utf-8")
            settings = Settings(home)
            settings.profile = {"person": {"name": "Sourav Sarker"}}
            from helpers import fetch_json, http_error, running
            with running(make_handler(settings)) as srv:
                with progress.track("cv", "Reading your CV again"):
                    progress.stage("Reading your CV and writing your profile", expect=1000)
                    progress.writing("x" * 250)
                    snap = fetch_json(f"{srv.base}/api/progress?task=cv")
                    self.assertTrue(snap["active"])
                    self.assertEqual(snap["percent"], 25)
                    req = urllib.request.Request(f"{srv.base}/api/cv/reread", data=b"{}", method="POST",
                                                 headers={"X-Jobhunt": "1", "Content-Type": "application/json"})
                    with mock.patch("stellenpilot.llm.LLM.enabled", new_callable=mock.PropertyMock, return_value=True):
                        code, _ = http_error(req)
                    self.assertEqual(code, 409)  # a second read while one runs is refused


if __name__ == "__main__":
    unittest.main()
