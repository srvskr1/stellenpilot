"""Shared test helpers for local HTTP servers. Everything opened here is closed again, so the suite
runs without ResourceWarnings (issue #21). Imported as `helpers`: run the tests with
python -m unittest discover -s tests"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer


class Server:
    """A ThreadingHTTPServer on a free local port, in a background thread."""

    def __init__(self, handler):
        self.handler = handler
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.srv.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()  # shutdown() only stops the loop; this closes the listening socket
        self._thread.join(5)
        close = getattr(self.handler, "close", None)  # the dashboard handler owns a database connection
        if callable(close):
            close()


@contextmanager
def running(handler):
    server = Server(handler)
    try:
        yield server
    finally:
        server.close()


def fetch(req, timeout: float = 10) -> bytes:
    """Body of a successful request. The response is always closed."""
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (local test server)
        return r.read()


def fetch_json(req, timeout: float = 10):
    return json.loads(fetch(req, timeout) or b"null")


def http_error(req, timeout: float = 10) -> tuple[int, dict]:
    """(status, JSON body) of a request that must fail. The error response is always closed."""
    try:
        with urllib.request.urlopen(req, timeout=timeout):  # noqa: S310
            pass
    except urllib.error.HTTPError as e:
        with e:
            raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {}
    raise AssertionError(f"expected an HTTP error for {getattr(req, 'full_url', req)}")
