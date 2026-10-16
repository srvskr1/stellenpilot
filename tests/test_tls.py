import ssl
import sys
import unittest
from unittest import mock

from stellenpilot import builtin, tls


class TestTls(unittest.TestCase):
    def test_system_store_is_used_when_truststore_is_there(self):
        try:
            import truststore  # noqa: F401
        except ImportError:
            self.skipTest("truststore not installed")
        self.assertTrue(tls.use_system_store())
        self.assertIn("truststore", type(ssl.create_default_context()).__module__)

    def test_missing_truststore_keeps_python_default(self):
        with mock.patch.object(tls, "_done", False), mock.patch.dict(sys.modules, {"truststore": None}):
            self.assertFalse(tls.use_system_store())

    def test_certificate_error_in_plain_words(self):
        e = OSError("<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>")
        self.assertIn("antivirus", builtin._plain(e))


if __name__ == "__main__":
    unittest.main()
