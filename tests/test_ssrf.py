"""Adding a job by link may only ever read public web pages (review: SSRF, DNS rebinding, proxies)."""
import http.server
import ipaddress
import os
import socket
import threading
import unittest
from unittest import mock

from stellenpilot import manual, pipeline
from stellenpilot.manual import AddError, FetchError, open_public, resolve_public

PUBLIC = "93.184.216.34"


def _info(ip, port=80):
    fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return [(fam, socket.SOCK_STREAM, 6, "", (ip, port))]


class Server:
    """A local web server that pretends to be public sites, reached through a patched connect."""
    def __init__(self, routes):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                code, headers, body = routes.get(self.headers["Host"].split(":")[0] + self.path, (404, {}, b"no"))
                self.send_response(code)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]
        self.connected = []

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()

    def connect(self, addr, timeout=None, *a, **k):
        self.connected.append(addr[0])
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # not create_connection: its lookup is patched
        sock.settimeout(timeout)
        sock.connect(("127.0.0.1", self.port))
        return sock


class RebindingTests(unittest.TestCase):
    def test_name_is_looked_up_once_and_that_address_is_used(self):
        answers = [_info(PUBLIC), _info("127.0.0.1")]  # first public, then rebinds to localhost
        calls = []

        def lookup(*a, **k):
            calls.append(a[0])
            return answers[min(len(calls) - 1, 1)]
        with mock.patch.object(manual.socket, "getaddrinfo", side_effect=lookup), \
                mock.patch.object(manual.socket, "create_connection", side_effect=ConnectionRefusedError) as connect:
            with self.assertRaises(ConnectionRefusedError):
                open_public("http://rebind.example/job")
        self.assertEqual(calls, ["rebind.example"])           # one lookup ...
        self.assertEqual(connect.call_args[0][0], (PUBLIC, 80))  # ... and the connection goes to that address

    def test_any_private_address_in_the_answer_is_refused(self):
        with mock.patch.object(manual.socket, "getaddrinfo", return_value=_info(PUBLIC) + _info("10.0.0.5")):
            with self.assertRaises(AddError):
                resolve_public("http://mixed.example/")

    def test_special_addresses(self):
        for ip in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1", "fe80::1",
                   "::ffff:127.0.0.1", "::ffff:10.0.0.1", "fc00::1", "224.0.0.1"):
            with self.subTest(ip=ip):
                self.assertFalse(manual._public(ipaddress.ip_address(ip)))
        self.assertTrue(manual._public(ipaddress.ip_address(PUBLIC)))

    def test_no_proxy_fallback_for_unknown_names(self):
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://corp-proxy:3128", "HTTP_PROXY": "http://corp-proxy:3128"}), \
                mock.patch.object(manual.socket, "getaddrinfo", side_effect=socket.gaierror("no such name")), \
                mock.patch.object(manual.socket, "create_connection") as connect:
            with self.assertRaises(AddError):
                open_public("https://intranet.corp/")
        connect.assert_not_called()

    def test_https_checks_the_certificate_for_the_site_name(self):
        conn = manual._PinnedHTTPS("jobs.example", PUBLIC, 443, 5)
        ctx = mock.MagicMock()
        conn._context = ctx
        with mock.patch.object(manual.socket, "create_connection", return_value=mock.MagicMock()) as connect:
            conn.connect()
        connect.assert_called_once_with((PUBLIC, 443), 5)
        self.assertEqual(ctx.wrap_socket.call_args.kwargs["server_hostname"], "jobs.example")
        self.assertTrue(manual._PinnedHTTPS("a", PUBLIC, 443, 5)._context.check_hostname)


class RedirectTests(unittest.TestCase):
    def setUp(self):
        self.site = Server({
            "jobs.example/a": (302, {"Location": "http://careers.example/b"}, b""),
            "careers.example/b": (200, {}, b"<h1>Data Engineer</h1>"),
            "jobs.example/evil": (302, {"Location": "http://127.0.0.1/admin"}, b""),
            "jobs.example/gone": (410, {}, b"gone"),
        })
        names = {"jobs.example": PUBLIC, "careers.example": "93.184.216.35"}
        self.lookup = mock.patch.object(manual.socket, "getaddrinfo",
                                         side_effect=lambda host, *a, **k: _info(names.get(host, "127.0.0.1")))
        self.connect = mock.patch.object(manual.socket, "create_connection", side_effect=self.site.connect)
        self.lookup.start()
        self.connect.start()

    def tearDown(self):
        self.lookup.stop()
        self.connect.stop()
        self.site.close()

    def test_redirect_to_another_public_site_is_followed(self):
        url, body = open_public("http://jobs.example/a")
        self.assertEqual((url, body), ("http://careers.example/b", b"<h1>Data Engineer</h1>"))
        self.assertEqual(self.site.connected, [PUBLIC, "93.184.216.35"])

    def test_redirect_to_a_local_address_is_refused_before_connecting(self):
        with self.assertRaises(AddError):
            open_public("http://jobs.example/evil")
        self.assertEqual(self.site.connected, [PUBLIC])  # the second hop was never contacted

    def test_closed_postings_are_marked(self):
        db = mock.MagicMock()
        db.jobs.return_value = [{"id": "g", "url": "http://jobs.example/gone"}]
        self.assertEqual(pipeline.check_closed(db), 1)
        db.update_job.assert_called_once()
        with self.assertRaises(FetchError):
            open_public("http://jobs.example/gone")


if __name__ == "__main__":
    unittest.main()
