from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from portfolio.imports.xp import asset_type, number, parse_date, parse_workbook


class XPParserTests(unittest.TestCase):
    def test_number_brazilian_format(self):
        self.assertEqual(number("1.234,56"), Decimal("1234.56"))
        self.assertEqual(number("R$ 12,30"), Decimal("12.30"))
        self.assertIsNone(number(None))

    def test_date_and_asset_type(self):
        self.assertEqual(parse_date("12/11/2026"), "2026-11-12")
        self.assertEqual(parse_date(datetime(2026, 11, 12)), "2026-11-12")
        self.assertEqual(asset_type("NVDC34"), "BDR")
        self.assertEqual(asset_type("ABCD11"), "FII")
        self.assertEqual(asset_type("PETR4"), "STOCK")

    def _make_workbook(self, path: Path):
        wb = Workbook()
        ws = wb.active
        ws.title = "Sua carteira"
        ws["F1"] = "Conta: 7737516 | 12/11/2026, 13:07"

        positions_total = Decimal("1700.00")
        incomes_gross = Decimal("10.00")
        ws["A4"] = float(positions_total + incomes_gross)

        for row_no in (9, 10, 11, 14):
            ws.cell(row_no, 1, f"STK{row_no}")
            ws.cell(row_no, 2, 100)
            ws.cell(row_no, 5, 10)
            ws.cell(row_no, 6, 10)
            ws.cell(row_no, 7, 10)

        ws.cell(20, 1, "Fundo de teste")
        ws.cell(20, 3, 100)
        ws.cell(20, 5, 90)
        ws.cell(20, 6, 95)

        for row_no in range(26, 38):
            ws.cell(row_no, 1, f"F{row_no:02d}11")
            ws.cell(row_no, 2, 100)
            ws.cell(row_no, 4, 10)
            ws.cell(row_no, 5, 10)
            ws.cell(row_no, 6, 10)

        ws.cell(6, 7, 400)
        ws.cell(17, 7, 100)
        ws.cell(23, 7, 1200)

        for row_no in list(range(47, 54)) + list(range(58, 61)):
            ws.cell(row_no, 1, "PETR4")
            ws.cell(row_no, 2, 1)
            ws.cell(row_no, 4, 1)
            ws.cell(row_no, 5, 0.9)
            ws.cell(row_no, 6, "DIVIDENDO")
            ws.cell(row_no, 7, "16/11/2026")

        ws.cell(44, 7, 7)
        ws.cell(55, 7, 3)
        wb.save(path)
        wb.close()

    def test_parse_workbook_without_database_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "xp.xlsx"
            self._make_workbook(path)
            data = parse_workbook(path)

        self.assertEqual(data["account_code"], "7737516")
        self.assertEqual(data["snapshot_date"], "2026-11-12")
        self.assertEqual(len(data["positions"]), 17)
        self.assertEqual(len(data["incomes"]), 10)
        self.assertTrue(all(data["checks"].values()))
        self.assertEqual(data["position_total"], Decimal("1700.0"))
        self.assertEqual(data["income_gross_total"], Decimal("10.0"))


if __name__ == "__main__":
    unittest.main()
