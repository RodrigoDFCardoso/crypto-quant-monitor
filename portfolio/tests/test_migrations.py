from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from portfolio.migrate import migrate_database, migration_status


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fresh_database_and_idempotency(self):
        first = migrate_database(self.db_path)
        second = migrate_database(self.db_path)

        self.assertEqual([version for version, _ in first], [1, 2])
        self.assertEqual(second, [])
        self.assertEqual([row[0] for row in migration_status(self.db_path)], [1, 2])

        with sqlite3.connect(self.db_path) as con:
            tables = {
                row[0]
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            expected = {
                "portfolio_accounts", "portfolio_assets", "portfolio_imports",
                "portfolio_positions", "portfolio_transactions", "portfolio_income",
                "portfolio_snapshots", "schema_migrations",
            }
            self.assertTrue(expected.issubset(tables))
            columns = {
                row[1] for row in con.execute("PRAGMA table_info(portfolio_positions)")
            }
            self.assertIn("invested_amount", columns)
            self.assertIn("net_liquidation_value", columns)
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_preserves_existing_scanner_tables_and_rows(self):
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "CREATE TABLE scanner_runs (id INTEGER PRIMARY KEY, run_label TEXT)"
            )
            con.execute(
                "INSERT INTO scanner_runs(id, run_label) VALUES (77, 'scanner-preservado')"
            )

        migrate_database(self.db_path)

        with sqlite3.connect(self.db_path) as con:
            self.assertEqual(
                con.execute(
                    "SELECT run_label FROM scanner_runs WHERE id=77"
                ).fetchone()[0],
                "scanner-preservado",
            )

    def test_adds_missing_columns_to_legacy_positions_table(self):
        with sqlite3.connect(self.db_path) as con:
            con.execute("""CREATE TABLE portfolio_positions (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                asset_id INTEGER NOT NULL,
                import_id INTEGER,
                snapshot_date TEXT NOT NULL,
                quantity REAL,
                average_cost REAL,
                market_price REAL,
                market_value REAL,
                currency TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'MANUAL',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            con.execute("""CREATE TABLE portfolio_accounts (
                id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT NOT NULL,
                broker TEXT NOT NULL, market TEXT NOT NULL, base_currency TEXT NOT NULL
            )""")
            con.execute("""CREATE TABLE portfolio_assets (
                id INTEGER PRIMARY KEY, market TEXT NOT NULL, symbol TEXT NOT NULL,
                asset_type TEXT NOT NULL, quote_currency TEXT NOT NULL,
                UNIQUE(market, symbol)
            )""")
            con.execute(
                "INSERT INTO portfolio_accounts VALUES (1, 'XP', 'XP', 'XP', 'B3', 'BRL')"
            )
            con.execute(
                "INSERT INTO portfolio_assets VALUES (1, 'B3', 'PETR4', 'STOCK', 'BRL')"
            )
            con.execute("""INSERT INTO portfolio_positions (
                id, account_id, asset_id, snapshot_date, quantity, average_cost,
                market_price, market_value, currency
            ) VALUES (5, 1, 1, '2026-11-12', 6, 42.08, 39.5, 237.0, 'BRL')""")

        migrate_database(self.db_path)

        with sqlite3.connect(self.db_path) as con:
            columns = {
                row[1] for row in con.execute("PRAGMA table_info(portfolio_positions)")
            }
            saved_position = con.execute(
                "SELECT quantity, average_cost, market_value "
                "FROM portfolio_positions WHERE id=5"
            ).fetchone()
        self.assertIn("invested_amount", columns)
        self.assertIn("net_liquidation_value", columns)
        self.assertEqual(saved_position, (6.0, 42.08, 237.0))


if __name__ == "__main__":
    unittest.main()
