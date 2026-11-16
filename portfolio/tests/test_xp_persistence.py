
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

from portfolio.imports.xp_persistence import import_xp_data
from portfolio.migrate import migrate_database
from portfolio.db import connect


def make_xp_data(
    *,
    account_code: str = "7737516",
    sha256: str = "a" * 64,
    snapshot_date: str = "2026-11-12",
    checks_ok: bool = True,
) -> dict[str, Any]:
    """Cria dados sintéticos para testar a persistência sem usar a planilha real."""

    positions = [
        {
            "symbol": "PETR4",
            "name": "Petrobras PN",
            "type": "STOCK",
            "quantity": 2,
            "average_cost": 40.0,
            "invested_amount": 80.0,
            "market_price": 45.0,
            "market_value": 90.0,
            "net_liquidation_value": 90.0,
        },
        {
            "symbol": "TREND_INVESTBACK_III_ONE",
            "name": "Trend Investback III",
            "type": "FUND",
            "quantity": None,
            "average_cost": None,
            "invested_amount": 90.0,
            "market_price": None,
            "market_value": 95.0,
            "net_liquidation_value": 92.0,
        },
    ]

    # Duas ocorrências idênticas para verificar a deduplicação por ocorrência.
    incomes = [
        {
            "symbol": "JPPA11",
            "quantity_reference": 10,
            "event_type": "RENDIMENTO",
            "gross_amount": 8.40,
            "net_amount": 8.40,
            "expected_payment_date": "2026-11-16",
        },
        {
            "symbol": "JPPA11",
            "quantity_reference": 10,
            "event_type": "RENDIMENTO",
            "gross_amount": 8.40,
            "net_amount": 8.40,
            "expected_payment_date": "2026-11-16",
        },
    ]

    return {
        "filename": "PosicaoDetalhada.xlsx",
        "sha256": sha256,
        "account_code": account_code,
        "snapshot_date": snapshot_date,
        "xp_total": 201.80,
        "positions": positions,
        "incomes": incomes,
        "section_totals": {
            "stocks": 90.0,
            "funds": 95.0,
            "fiis": 0.0,
        },
        "position_total": 185.0,
        "income_gross_total": 16.80,
        "income_net_total": 16.80,
        "checks": {
            "synthetic_validation": checks_ok,
        },
    }


class TestXPPersistence(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_portfolio.db"
        migrate_database(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        con = connect(self.db_path)
        try:
            return con.execute(sql, params).fetchall()
        finally:
            con.close()

    def count(self, table: str) -> int:
        rows = self.query(f"SELECT COUNT(*) AS total FROM {table}")
        return rows[0]["total"]

    def test_successful_import(self) -> None:
        data = make_xp_data()

        result = import_xp_data(data, self.db_path)

        self.assertFalse(result["already_imported"])
        self.assertEqual(result["positions_inserted"], 2)
        self.assertEqual(result["incomes_inserted"], 2)
        self.assertEqual(result["incomes_duplicated"], 0)

        self.assertEqual(self.count("portfolio_accounts"), 1)
        self.assertEqual(self.count("portfolio_assets"), 3)
        self.assertEqual(self.count("portfolio_imports"), 1)
        self.assertEqual(self.count("portfolio_positions"), 2)
        self.assertEqual(self.count("portfolio_income"), 2)
        self.assertEqual(self.count("portfolio_snapshots"), 1)
        self.assertEqual(self.count("portfolio_transactions"), 0)

        imported = self.query(
            "SELECT status, row_count FROM portfolio_imports"
        )[0]

        self.assertEqual(imported["status"], "IMPORTED")
        self.assertEqual(imported["row_count"], 4)

        jppa = self.query(
            """
            SELECT a.symbol, a.asset_type, COUNT(p.id) AS position_count
            FROM portfolio_assets a
            LEFT JOIN portfolio_positions p ON p.asset_id = a.id
            WHERE a.symbol = 'JPPA11'
            GROUP BY a.id
            """
        )[0]

        self.assertEqual(jppa["symbol"], "JPPA11")
        self.assertEqual(jppa["asset_type"], "FII")
        self.assertEqual(jppa["position_count"], 0)

        fund = self.query(
            """
            SELECT quantity, average_cost, market_price,
                   invested_amount, market_value, net_liquidation_value
            FROM portfolio_positions p
            JOIN portfolio_assets a ON a.id = p.asset_id
            WHERE a.symbol = 'TREND_INVESTBACK_III_ONE'
            """
        )[0]

        self.assertIsNone(fund["quantity"])
        self.assertIsNone(fund["average_cost"])
        self.assertIsNone(fund["market_price"])
        self.assertAlmostEqual(fund["invested_amount"], 90.0)
        self.assertAlmostEqual(fund["market_value"], 95.0)
        self.assertAlmostEqual(fund["net_liquidation_value"], 92.0)

        snapshot = self.query(
            """
            SELECT total_market_value, available_cash, pending_income
            FROM portfolio_snapshots
            """
        )[0]

        self.assertAlmostEqual(snapshot["total_market_value"], 185.0)
        self.assertAlmostEqual(snapshot["available_cash"], 0.0)
        self.assertAlmostEqual(snapshot["pending_income"], 16.80)

        integrity = self.query("PRAGMA integrity_check")[0][0]
        self.assertEqual(integrity, "ok")

    def test_same_file_is_not_imported_twice(self) -> None:
        data = make_xp_data()

        first = import_xp_data(data, self.db_path)
        second = import_xp_data(data, self.db_path)

        self.assertFalse(first["already_imported"])
        self.assertTrue(second["already_imported"])
        self.assertEqual(first["import_id"], second["import_id"])

        self.assertEqual(self.count("portfolio_accounts"), 1)
        self.assertEqual(self.count("portfolio_assets"), 3)
        self.assertEqual(self.count("portfolio_imports"), 1)
        self.assertEqual(self.count("portfolio_positions"), 2)
        self.assertEqual(self.count("portfolio_income"), 2)
        self.assertEqual(self.count("portfolio_snapshots"), 1)

    def test_different_file_same_snapshot_date_is_rejected(self) -> None:
        first_data = make_xp_data(sha256="a" * 64)
        second_data = make_xp_data(sha256="b" * 64)

        import_xp_data(first_data, self.db_path)

        with self.assertRaises(ValueError):
            import_xp_data(second_data, self.db_path)

        self.assertEqual(self.count("portfolio_accounts"), 1)
        self.assertEqual(self.count("portfolio_imports"), 1)
        self.assertEqual(self.count("portfolio_positions"), 2)
        self.assertEqual(self.count("portfolio_income"), 2)
        self.assertEqual(self.count("portfolio_snapshots"), 1)

    
    def test_same_income_across_different_snapshots_is_deduplicated(self) -> None:
        first_data = make_xp_data(
            sha256="a" * 64,
            snapshot_date="2026-11-12",
        )
        second_data = make_xp_data(
            sha256="b" * 64,
            snapshot_date="2026-11-19",
        )

        first = import_xp_data(first_data, self.db_path)
        second = import_xp_data(second_data, self.db_path)

        self.assertFalse(first["already_imported"])
        self.assertFalse(second["already_imported"])

        self.assertEqual(first["incomes_inserted"], 2)
        self.assertEqual(second["incomes_inserted"], 0)
        self.assertEqual(second["incomes_duplicated"], 2)

        self.assertEqual(self.count("portfolio_imports"), 2)
        self.assertEqual(self.count("portfolio_positions"), 4)
        self.assertEqual(self.count("portfolio_income"), 2)
        self.assertEqual(self.count("portfolio_snapshots"), 2)

    def test_new_payment_date_creates_new_income_records(self) -> None:
        first_data = make_xp_data(
            sha256="a" * 64,
            snapshot_date="2026-11-12",
        )
        second_data = make_xp_data(
            sha256="b" * 64,
            snapshot_date="2026-11-19",
        )

        for item in second_data["incomes"]:
            item["expected_payment_date"] = "2026-12-16"

        first = import_xp_data(first_data, self.db_path)
        second = import_xp_data(second_data, self.db_path)

        self.assertEqual(first["incomes_inserted"], 2)
        self.assertEqual(second["incomes_inserted"], 2)
        self.assertEqual(second["incomes_duplicated"], 0)

        self.assertEqual(self.count("portfolio_income"), 4)
        self.assertEqual(self.count("portfolio_snapshots"), 2)

        dates = self.query(
            """
            SELECT DISTINCT expected_payment_date
            FROM portfolio_income
            ORDER BY expected_payment_date
            """
        )

        self.assertEqual(
            [row["expected_payment_date"] for row in dates],
            ["2026-11-16", "2026-12-16"],
        )


    def test_wrong_account_is_rejected_without_writes(self) -> None:
        data = make_xp_data(account_code="9999999")

        with self.assertRaisesRegex(ValueError, "não autorizada"):
            import_xp_data(data, self.db_path)

        # O banco e o schema já existem por causa do setUp().
        # A conta não autorizada não deve gerar nenhum registro.
        self.assertEqual(self.count("portfolio_accounts"), 0)
        self.assertEqual(self.count("portfolio_assets"), 0)
        self.assertEqual(self.count("portfolio_imports"), 0)
        self.assertEqual(self.count("portfolio_positions"), 0)
        self.assertEqual(self.count("portfolio_income"), 0)
        self.assertEqual(self.count("portfolio_snapshots"), 0)
        self.assertEqual(self.count("portfolio_transactions"), 0)

    def test_failed_parser_validation_is_rejected(self) -> None:
        data = make_xp_data(checks_ok=False)

        with self.assertRaises(ValueError):
            import_xp_data(data, self.db_path)

        self.assertEqual(self.count("portfolio_accounts"), 0)
        self.assertEqual(self.count("portfolio_assets"), 0)
        self.assertEqual(self.count("portfolio_imports"), 0)
        self.assertEqual(self.count("portfolio_positions"), 0)
        self.assertEqual(self.count("portfolio_income"), 0)
        self.assertEqual(self.count("portfolio_snapshots"), 0)

    def test_failure_rolls_back_entire_import(self) -> None:
        con = connect(self.db_path)
        try:
            con.execute(
                """
                CREATE TRIGGER fail_snapshot_insert
                BEFORE INSERT ON portfolio_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'forced snapshot failure');
                END
                """
            )
            con.commit()
        finally:
            con.close()

        data = make_xp_data()

        with self.assertRaisesRegex(sqlite3.IntegrityError, "forced snapshot failure"):
            import_xp_data(data, self.db_path)

        self.assertEqual(self.count("portfolio_accounts"), 0)
        self.assertEqual(self.count("portfolio_assets"), 0)
        self.assertEqual(self.count("portfolio_imports"), 0)
        self.assertEqual(self.count("portfolio_positions"), 0)
        self.assertEqual(self.count("portfolio_income"), 0)
        self.assertEqual(self.count("portfolio_snapshots"), 0)
        self.assertEqual(self.count("portfolio_transactions"), 0)

        integrity = self.query("PRAGMA integrity_check")[0][0]
        self.assertEqual(integrity, "ok")


if __name__ == "__main__":
    unittest.main()

