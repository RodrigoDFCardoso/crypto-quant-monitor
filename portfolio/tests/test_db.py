from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from portfolio.db import connect, get_db_path


class DatabaseConnectionTests(unittest.TestCase):
    def test_connection_pragmas(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "database.db"
            con = connect(path)
            try:
                self.assertEqual(con.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                self.assertTrue(path.exists())
            finally:
                con.close()

    def test_explicit_database_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "custom.db"
            self.assertEqual(get_db_path(path), path.resolve())


if __name__ == "__main__":
    unittest.main()
