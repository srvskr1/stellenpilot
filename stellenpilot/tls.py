"""Check secure connections with the computer's own certificate store.

Python on Windows reads only the root certificates already in the Windows store. Windows adds most roots
the first time a browser needs them, and antivirus programs and company proxies add their own, so
Python can fail with CERTIFICATE_VERIFY_FAILED on a site the browser opens fine. truststore asks the
operating system to check the certificate instead, the way the browser does. pip does the same.
"""
from __future__ import annotations

_done = False


def use_system_store() -> bool:
    """Make every secure connection in this process use the system's certificate check. Safe to call
    more than once. Returns False when truststore is not installed; Python's own check then stays."""
    global _done
    if _done:
        return True
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001 (missing or unsupported: keep Python's default check)
        return False
    _done = True
    return True
