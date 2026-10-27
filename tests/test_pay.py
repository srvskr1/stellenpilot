"""Pay and deadline reading from ad text, Blue Card line, comparison with the person's own jobs."""
import unittest
from datetime import date

from stellenpilot.pay import PENSION_CEILING, blue_card, blue_card_info, blue_card_lines, deadline, fill_pay, salary


class SalaryTests(unittest.TestCase):
    def test_reads_common_german_and_english_forms(self):
        cases = {
            "Gehalt: 55.000 - 65.000 € brutto im Jahr": (55000, 65000),
            "Wir bieten ein Jahresgehalt von 60.000 EUR.": (60000, 60000),
            "Salary range: €58,000 to €68,000 per year": (58000, 68000),
            "Salary: 55k - 70k € depending on experience": (55000, 70000),
            "Vergütung: 4.500 € brutto monatlich": (54000, 54000),
            "Zielgehalt 45.934,20 € p.a.": (45934, 45934),
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(salary(text), want)

    def test_ignores_what_is_not_the_salary(self):
        for text in ("Weiterbildungsbudget von 2.000 € pro Jahr", "15 € pro Stunde brutto", "Umsatz von 50.000.000 €",
                     "From 2020 - 2023 you worked", "Team of 1.200 Mitarbeiter", "Bonus: 5.000 € jährlich", "No pay here."):
            with self.subTest(text=text):
                self.assertIsNone(salary(text))

    def test_a_ceiling_is_not_the_pay(self):
        # "up to" says nothing about the floor, so it must not pass the Blue Card check
        for text in ("Salary: up to €60k per year", "Gehalt bis zu 60.000 € brutto", "Jahresgehalt max. 65k €",
                     "Vergütung höchstens 58.000 EUR p.a."):
            with self.subTest(text=text):
                self.assertIsNone(salary(text))
        # a floor and a "bis" range still read
        self.assertEqual(salary("Gehalt: ab 55k € brutto im Jahr"), (55000, 55000))
        self.assertEqual(salary("Jahresgehalt 55.000 bis 65.000 EUR"), (55000, 65000))


class DeadlineTests(unittest.TestCase):
    def test_reads_stated_deadlines(self):
        self.assertEqual(deadline("Bewerbungsfrist: 31.10.2026", "2026-10-20"), "2026-10-31")
        self.assertEqual(deadline("Please apply by 15 November 2026.", "2026-10-20"), "2026-11-15")
        self.assertEqual(deadline("Bewerbungen bis zum 5. Januar", "2026-12-01"), "2027-01-05")

    def test_no_deadline_or_nonsense(self):
        self.assertEqual(deadline("Start: 01.01.2027, unbefristet", "2026-10-20"), "")
        self.assertEqual(deadline("Bewerbungsfrist: 01.01.2020", "2026-10-20"), "")


class BlueCardTests(unittest.TestCase):
    def test_verdicts_and_stale_warning(self):
        today = date(2026, 6, 1)
        self.assertEqual(blue_card(50700, today)["verdict"], "yes")
        self.assertEqual(blue_card(45935, today)["verdict"], "shortage")
        self.assertEqual(blue_card(40000, today)["verdict"], "no")
        self.assertFalse(blue_card(60000, today)["stale"])
        self.assertTrue(blue_card(60000, date(max(PENSION_CEILING) + 1, 1, 2))["stale"])

    def test_lines_follow_the_pension_ceiling(self):
        self.assertEqual(blue_card_lines(2026), {"year": 2026, "regular": 50700, "shortage": 45934.2})
        self.assertEqual(blue_card_lines(2025), {"year": 2025, "regular": 48300, "shortage": 43759.8})
        self.assertEqual(blue_card_lines(2099)["year"], max(PENSION_CEILING))  # no newer ceiling: last known one
        self.assertEqual(blue_card(45934, date(2026, 6, 1))["verdict"], "no")  # 20 cents short of 45,934.20

    def test_next_year_is_not_used_before_1_january(self):
        # 2027 is in the table already; a job checked in December must still get the 2026 lines
        dec, jan = blue_card_info(date(2026, 12, 31)), blue_card_info(date(2027, 1, 1))
        self.assertEqual((dec["year"], dec["regular"], dec["final"]), (2026, 50700, True))
        self.assertEqual((jan["year"], jan["regular"], jan["shortage"]), (2027, 53100, 48108.6))
        self.assertFalse(jan["final"])  # cabinet figure, Bundesrat approval pending
        self.assertEqual(blue_card(52000, date(2026, 12, 31))["verdict"], "yes")
        self.assertEqual(blue_card(52000, date(2027, 1, 1))["verdict"], "shortage")

    def test_every_year_shown_has_an_official_dated_source(self):
        for y in range(2026, max(PENSION_CEILING) + 1):
            info = blue_card_info(date(y, 6, 1))
            self.assertRegex(info["url"], r"^https://www\.(bundesanzeiger|bundesregierung)\.de/")
            date.fromisoformat(info["checked"])


class CompareTests(unittest.TestCase):
    def jobs(self, n, city="Essen", pay=60000):
        return [{"id": f"{city}{i}", "title": "Data Engineer", "location": city, "found_at": "2026-10-01",
                 "description": f"Gehalt: {pay + i * 1000:,} € brutto".replace(",", ".")} for i in range(n)]

    def test_compares_with_same_city_when_enough_ads(self):
        jobs = self.jobs(5, "Essen") + self.jobs(5, "Berlin", 80000)
        fill_pay(jobs)
        self.assertEqual(jobs[0]["pay"]["near"], "Essen")
        self.assertEqual(jobs[0]["pay"]["median"], 62000)
        self.assertEqual(jobs[0]["pay"]["fair"], "average")

    def test_too_few_ads_gives_no_verdict(self):
        jobs = self.jobs(4)
        fill_pay(jobs)
        self.assertIsNone(jobs[0]["pay"]["fair"])
        self.assertEqual(jobs[0]["pay"]["lo"], 60000)

    def test_ads_without_pay_get_a_hint(self):
        jobs = self.jobs(5) + [{"id": "x", "title": "Data Engineer", "location": "Essen", "description": "No pay stated."}]
        fill_pay(jobs)
        self.assertIsNone(jobs[-1]["pay"])
        self.assertEqual(jobs[-1]["payHint"]["peers"], 5)


if __name__ == "__main__":
    unittest.main()
