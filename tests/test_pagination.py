import unittest
from unittest import mock

from stellenpilot.sources import adzuna, arbeitsagentur


class S:
    def __init__(self, limits):
        self.cfg = {"search": {"keywords": ["Data A", "Data B"], "city": "Essen", "radius_km": 50, "country": "de",
                               "max_age_days": 3, "include_remote": False, "exclude_title_words": []},
                    "sources": {"limits": limits}}

    def __getitem__(self, k):
        return self.cfg[k]

    @staticmethod
    def secret(name):
        return "x"


def az_page(n, start):
    return {"results": [{"id": start + i, "title": f"Job {start + i}", "description": "", "created": "2026-10-10"} for i in range(n)]}


class AdzunaPaging(unittest.TestCase):
    def test_breadth_first_and_budget(self):
        calls = []

        def fake(url, params=None, **kw):
            page = int(url.rsplit("/", 1)[1])
            calls.append((params["what"], page))
            if params["what"] == "Data A":
                return az_page(50 if page < 3 else 10, page * 1000)  # three pages, last one short
            return az_page(5, 90000)  # one short page
        with mock.patch.object(adzuna, "request_json", side_effect=fake):
            jobs = adzuna.fetch(S({"adzuna_calls": 20, "adzuna_pages": 5}))
        self.assertEqual(calls, [("Data A", 1), ("Data B", 1), ("Data A", 2), ("Data A", 3)])
        self.assertEqual(len(jobs), 50 + 5 + 50 + 10)
        with mock.patch.object(adzuna, "request_json", side_effect=fake) as m:
            adzuna.fetch(S({"adzuna_calls": 3, "adzuna_pages": 5}))
        self.assertEqual(m.call_count, 3)  # never more calls than the budget


class BAPaging(unittest.TestCase):
    def test_follows_pages_until_short_page_or_cap(self):
        def page(params):
            n = arbeitsagentur.PAGE_SIZE if params["page"] < 3 else 7
            base = params["page"] * 1000 + (0 if params["was"] == "Data A" else 500)
            return [{"referenznummer": f"R{base + i}", "stellenangebotsTitel": "Data job"} for i in range(n)]
        with mock.patch.object(arbeitsagentur, "_search", side_effect=page) as m, \
             mock.patch.object(arbeitsagentur, "_details", return_value={}):
            jobs = arbeitsagentur.fetch(S({"arbeitsagentur_results": 1000, "arbeitsagentur_pages": 5}))
        self.assertEqual(len(jobs), 2 * (2 * arbeitsagentur.PAGE_SIZE + 7))
        self.assertEqual(m.call_count, 6)
        with mock.patch.object(arbeitsagentur, "_search", side_effect=page), \
             mock.patch.object(arbeitsagentur, "_details", return_value={}):
            self.assertEqual(len(arbeitsagentur.fetch(S({"arbeitsagentur_results": 60}))), 60)


if __name__ == "__main__":
    unittest.main()
