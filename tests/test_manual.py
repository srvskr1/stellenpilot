"""Adding jobs by hand."""
import unittest

from stellenpilot.manual import AddError, build_job, fetch_page, job_from_jsonld

PAGE = """<html><head><title>Careers</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Data Analyst (m/w/d)",
"hiringOrganization":{"@type":"Organization","name":"Acme GmbH"},"jobLocation":{"@type":"Place","address":{"addressLocality":"Essen"}},
"datePosted":"2026-10-05","description":"&lt;p&gt;SQL and Python&lt;/p&gt;"}</script></head><body>x</body></html>"""


class ManualAddTests(unittest.TestCase):
    def test_jsonld_job_posting(self):
        j = job_from_jsonld(PAGE)
        self.assertEqual((j["title"], j["company"], j["location"], j["posted_at"]), ("Data Analyst (m/w/d)", "Acme GmbH", "Essen", "2026-10-05"))
        self.assertIn("SQL and Python", j["description"])

    def test_never_fetches_sites_that_forbid_it(self):
        for url in ("https://www.linkedin.com/jobs/view/1", "https://www.stepstone.de/stellenangebote--x", "https://de.indeed.com/viewjob?jk=1"):
            with self.assertRaises(AddError):
                fetch_page(url)

    def test_pasted_text_needs_title_and_company_without_llm(self):
        with self.assertRaises(AddError):
            build_job(text="Some ad about SQL")
        j = build_job(text="Some ad about SQL", title="Data Analyst", company="Acme")
        self.assertTrue(j["id"].startswith("me-"))
        self.assertEqual(j["source"], "Added by you")


if __name__ == "__main__":
    unittest.main()


class SmartRecruitersLinkTests(unittest.TestCase):
    def test_job_link_reads_single_posting(self):
        from unittest import mock
        from stellenpilot.manual import job_from_feed
        posting = {"name": "Working Student Data", "company": {"name": "Bosch"}, "location": {"city": "Stuttgart", "country": "de"},
                   "postingUrl": "https://jobs.smartrecruiters.com/BoschGroup/744000111111111", "releasedDate": "2026-10-01T00:00:00Z",
                   "jobAd": {"sections": {"jobDescription": {"text": "<p>Python and SQL</p>"}}}}
        with mock.patch("stellenpilot.http.request_json", return_value=posting), \
             mock.patch("stellenpilot.sources.watchlist.request_json", return_value=posting):
            job = job_from_feed("https://jobs.smartrecruiters.com/BoschGroup/744000111111111-working-student-data")
        self.assertEqual(job["title"], "Working Student Data")
        self.assertIn("Python and SQL", job["description"])


class SafeFetchTests(unittest.TestCase):
    """Adding by link must only ever read public web pages (review finding: SSRF)."""
    @classmethod
    def setUpClass(cls):
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<title>Internal admin</title>SECRET")
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_local_and_special_addresses_are_refused(self):
        port = self.srv.server_address[1]
        for url in (f"http://127.0.0.1:{port}/", f"http://localhost:{port}/", "http://169.254.169.254/latest/",
                    "http://[::1]/", "file:///etc/passwd", "ftp://example.com/x"):
            with self.subTest(url=url), self.assertRaises(AddError):
                fetch_page(url)

    def test_blocked_sites_in_any_letter_case(self):
        for url in ("HTTPS://www.linkedin.com/jobs/view/1", "Https://de.indeed.com/viewjob", "https://lnkd.in/abc"):
            with self.subTest(url=url), self.assertRaises(AddError):
                fetch_page(url)

    def test_redirect_to_local_address_is_refused(self):
        from stellenpilot.manual import _CheckedRedirects
        import urllib.request
        req = urllib.request.Request("https://example.com/")
        with self.assertRaises(AddError):
            _CheckedRedirects().redirect_request(req, None, 302, "Found", {}, f"http://127.0.0.1:{self.srv.server_address[1]}/")

    def test_bad_link_with_pasted_text_is_refused(self):
        with self.assertRaises(AddError):
            build_job(url="javascript:alert(1)", text="ad text", title="t", company="c")


class JsonLdShapeTests(unittest.TestCase):
    """schema.org allows text, lists or objects in many fields; none of them may crash adding a job."""
    def test_unusual_shapes(self):
        cases = {
            '{"@type":"JobPosting","title":"Data Engineer","hiringOrganization":{"name":"Acme"},"jobLocation":{"address":"Berlin"},"description":"x"}': "Berlin",
            '{"@type":"JobPosting","title":"Data Engineer","hiringOrganization":"Acme","jobLocation":[{"address":{"addressLocality":["Köln","Bonn"]}}],"description":"x"}': "Köln, Bonn",
            '{"@type":"JobPosting","title":{"@value":"Data Engineer"},"hiringOrganization":{"name":"Acme"},"description":"x"}': "",
        }
        for block, place in cases.items():
            with self.subTest(block=block[:60]):
                r = job_from_jsonld(f'<script type="application/ld+json">{block}</script>')
                self.assertEqual((r["title"], r["company"], r["location"]), ("Data Engineer", "Acme", place))
