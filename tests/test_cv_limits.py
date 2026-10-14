"""A small CV file must not unpack into gigabytes (review: decompression bomb), and on/off
settings must be read by meaning (review: bool("false") is True)."""
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from stellenpilot import importer
from stellenpilot.server import clean_settings


def _bomb_docx(path: Path, unpacked: int) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", b"\0" * unpacked)


def _pdf_with_stream(path: Path, raw: bytes) -> None:
    """A one page PDF whose page content is `raw`, Flate compressed, with a standard font."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    w = PdfWriter()
    page = w.add_blank_page(612, 792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    content = DecodedStreamObject()
    content.set_data(raw)
    page[NameObject("/Contents")] = w._add_object(content.flate_encode())
    with open(path, "wb") as f:
        w.write(f)


class BombTests(unittest.TestCase):
    def test_docx_that_unpacks_too_big_is_not_opened(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "cv.docx"
            _bomb_docx(f, 60_000_000)
            self.assertLess(f.stat().st_size, 200_000)  # tiny on disk ...
            t = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, "unpacks to far more"):
                importer.read_cv_text(f)
            self.assertLess(time.monotonic() - t, 2)   # ... and refused without unpacking it

    def test_not_a_zip(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "cv.docx"
            f.write_bytes(b"not a zip at all" * 10)
            with self.assertRaisesRegex(RuntimeError, "not a valid Word file"):
                importer.read_cv_text(f)

    def test_pdf_stream_that_unpacks_too_big_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "cv.pdf"
            _pdf_with_stream(f, b"BT /F1 12 Tf 72 720 Td (x) Tj ET " + b" " * 40_000_000)  # 40 MB in about 40 KB
            self.assertLess(f.stat().st_size, 200_000)
            with self.assertRaisesRegex(RuntimeError, "Could not read this PDF"):  # pypdf's own default would allow 75 MB
                importer.read_cv_text(f)

    def test_normal_pdf_still_reads(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "cv.pdf"
            text = b"BT /F1 12 Tf 72 720 Td (Alex Kumar Data Engineer Python SQL AWS Airflow dbt Kafka) Tj ET"
            _pdf_with_stream(f, text)
            self.assertIn("Alex Kumar Data Engineer", importer._read_any(f))

    def test_big_text_file_is_cut(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "cv.txt"
            f.write_text("Python SQL " * 1_000_000, encoding="utf-8")
            self.assertLessEqual(len(importer._read_any(f)), importer.MAX_CV_CHARS)


class SwitchTests(unittest.TestCase):
    def test_text_is_read_by_meaning(self):
        for given, want in (("false", False), ("False", False), ("0", False), ("off", False), ("", False), (0, False),
                            (False, False), (None, False), ("true", True), ("1", True), ("on", True), (1, True), (True, True)):
            with self.subTest(given=given):
                self.assertIs(clean_settings({"search": {"include_remote": given}})["search"]["include_remote"], want)

    def test_anything_else_is_refused(self):
        for given in ("maybe", 2, [True], {"a": 1}, 0.5):
            with self.subTest(given=given), self.assertRaises(ValueError):
                clean_settings({"schedule": {"enabled": given}})


if __name__ == "__main__":
    unittest.main()
