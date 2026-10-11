"""German level detection on real ad phrases."""
import unittest

from jobradar.text import german_too_high, required_german_level

CASES = {
    "Sehr gute Deutsch- und Englischkenntnisse in Wort und Schrift": "C1",
    "Verhandlungssichere Deutschkenntnisse": "C1",
    "Fließende Deutschkenntnisse (mind. B2)": "B2",
    "Gute Deutschkenntnisse": "B2",
    "Deutschkenntnisse von Vorteil": None,
    "German is a plus, English is our working language": None,
    "Fluent English; basic German": "A2",
    "Fluent English and basic German": "A2",
    "Sehr gute Englischkenntnisse. Grundkenntnisse in Deutsch.": "A2",
    "German C1 required": "C1",
    "Deutsch auf Muttersprachniveau": "C2",
    "Fluent in English and German": "B2",
    "You speak excellent English": None,
    "Good knowledge of SQL. German skills are nice to have.": None,
    "Du sprichst fließend Deutsch und Englisch": "B2",
    "Wir sind ein deutsches Unternehmen mit guten Produkten": None,
    "We are a German company with very good benefits": None,
    "Very good German and English skills": "C1",
    "Sehr gute deutsche Sprachkenntnisse": "C1",
    "Kommunikationsstarke Persönlichkeit mit sehr guten Deutsch- und Englischkenntnissen": "C1",
}


class GermanLevelTests(unittest.TestCase):
    def test_phrases(self):
        for text, expected in CASES.items():
            with self.subTest(text=text):
                self.assertEqual(required_german_level(text), expected)

    def test_tolerance(self):
        self.assertFalse(german_too_high("B1", "A2"))      # one step above is fine by default
        self.assertTrue(german_too_high("B2", "A2"))
        self.assertFalse(german_too_high(None, "A2"))
        self.assertTrue(german_too_high("B1", "A2", tolerance=0))


if __name__ == "__main__":
    unittest.main()


class RealAdPhrasesTests(unittest.TestCase):
    """Phrases taken from real ads where the first version was wrong."""
    def test_sichere_deutschkenntnisse_is_b2(self):
        self.assertEqual(required_german_level("Sichere Deutschkenntnisse in Wort und Schrift runden Dein Profil ab."), "B2")

    def test_fluent_english_german_bonus_is_optional(self):
        self.assertIsNone(required_german_level("Languages: Fluent English (German is a bonus), a collaborative mindset."))

    def test_german_university_is_not_a_language(self):
        self.assertIsNone(required_german_level("Currently enrolled at a German university and able to commute."))


class LetterLanguageTests(unittest.TestCase):
    def test_auto_writes_german_only_from_b2(self):
        from unittest import mock
        from jobradar.tailor import letter_language
        llm = mock.Mock(enabled=True)
        ad = {"title": "Werkstudent Daten", "description": "Wir suchen dich für unser Team und die Arbeit mit Daten und Kunden."}
        self.assertEqual(letter_language(ad, "auto", llm, "A2"), "en")
        self.assertEqual(letter_language(ad, "auto", llm, "B2"), "de")
        self.assertEqual(letter_language(ad, "de", llm, "A2"), "de")  # an explicit choice wins


class ReviewPhraseTests(unittest.TestCase):
    """Phrases where an earlier version was wrong (found in review)."""
    CASES = {
        "Verhandlungssichere Deutschkenntnisse, Englisch von Vorteil": "C1",
        "Fluent German is a must, English is a plus": "B2",
        "Fluent German required, English would be an asset": "B2",
        "Deutsch C1 - Englisch nice to have": "C1",
        "Deutsch: sehr gut, Englisch: von Vorteil": "C1",
        "Kenntnisse in Deutsch (B2) sind Pflicht, Englisch optional": "B2",
        "Deutschkenntnisse (mind. B2)": "B2",
        "Deutschkenntnisse auf mind. B2-Niveau": "B2",
        "German (min. C1)": "C1",
        "Native German is a plus": None,
        "Deutsch als Muttersprache ist von Vorteil": None,
        "Very good knowledge of English, German knowledge an advantage": None,
        "German-speaking customers, fluent English": None,
        "Deutsch B2/C1": "C1",
        "fluent English and basic German": "A2",
        "Fluent in English and German": "B2",
        "Deutsch und Englisch von Vorteil": None,
        "Fluent English or German": None,
    }

    def test_phrases(self):
        for text, want in self.CASES.items():
            with self.subTest(text=text):
                self.assertEqual(required_german_level(text), want)

    def test_own_level_words(self):
        from jobradar.text import normalize_level
        self.assertEqual(normalize_level("B2+"), "B2")
        self.assertEqual(normalize_level("native"), "C2")
        self.assertEqual(normalize_level("Muttersprache"), "C2")
        self.assertIsNone(normalize_level("so so"))
        self.assertFalse(german_too_high("C1", "native"))

