"""The database file carries a schema version and upgrades itself once, in order."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from stellenpilot import db as dbmod
from stellenpilot.db import DB, SCHEMA_VERSION


def version(path: Path) -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


def old_database(path: Path) -> None:
    """A database from before versioning: no german_level or summary_en, no run_log, user_version 0."""
    schema = dbmod.SCHEMA.split("CREATE TABLE IF NOT EXISTS run_log")[0]
    schema = schema.replace("  dedupe_key TEXT NOT NULL DEFAULT '',", "  dedupe_key TEXT NOT NULL DEFAULT ''")
    schema = "\n".join(l for l in schema.splitlines() if "german_level" not in l and "summary_en" not in l)
    con = sqlite3.connect(path)
    con.executescript(schema + """
      INSERT INTO jobs (id, source, title, found_at) VALUES ('a1', 'demo', 'Data Engineer', '2026-10-01');
      INSERT INTO runs (date, found, stage) VALUES ('2026-10-01', 3, 'done');""")
    con.commit()
    con.close()


class MigrationTest(unittest.TestCase):
    def test_fresh_database_is_at_current_version_without_backup(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "j.db"
            DB(path).conn.close()
            self.assertEqual(version(path), SCHEMA_VERSION)
            self.assertEqual(list(Path(d).glob("*.bak-*")), [])

    def test_old_database_is_upgraded_and_backed_up_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "j.db"
            old_database(path)
            db = DB(path)
            cols = {r[1] for r in db.conn.execute("PRAGMA table_info(jobs)")}
            self.assertIn("german_level", cols)
            self.assertIn("summary_en", cols)
            self.assertEqual(db.job("a1")["title"], "Data Engineer")  # user data survives
            self.assertEqual(len(db.history()), 1)
            db.conn.close()
            self.assertEqual(version(path), SCHEMA_VERSION)
            backup = Path(d) / "j.db.bak-v0"
            self.assertTrue(backup.is_file())
            self.assertEqual(version(backup), 0)  # the backup is the untouched old file
            DB(path).conn.close()  # second start: nothing to do, no new backup
            self.assertEqual(len(list(Path(d).glob("*.bak-*"))), 1)

    def test_failed_step_rolls_back_and_keeps_old_version(self):
        def broken(conn):
            conn.execute("ALTER TABLE jobs ADD COLUMN half_done TEXT")
            raise RuntimeError("step failed")

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "j.db"
            DB(path).conn.close()
            with mock.patch.object(dbmod, "MIGRATIONS", [*dbmod.MIGRATIONS, broken]), \
                 mock.patch.object(dbmod, "SCHEMA_VERSION", SCHEMA_VERSION + 1):
                with self.assertRaises(RuntimeError):
                    DB(path)
            self.assertEqual(version(path), SCHEMA_VERSION)
            con = sqlite3.connect(path)
            cols = {r[1] for r in con.execute("PRAGMA table_info(jobs)")}
            con.close()
            self.assertNotIn("half_done", cols)  # nothing half applied


if __name__ == "__main__":
    unittest.main()
