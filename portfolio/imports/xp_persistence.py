
from __future__ import annotations

import hashlib
import json
import sqlite3
from decimal import Decimal
from typing import Any

from portfolio.db import connect


ACCOUNT_NAME = "XP Investimentos - Conta 7737516"
BROKER = "XP"
MARKET = "B3"
CURRENCY = "BRL"
SOURCE = "XP_IMPORT"


def _as_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _income_dedupe_key(
    account_id: int,
    asset_symbol: str,
    item: dict[str, Any],
) -> str:
    identity = {
        "account_id": account_id,
        "symbol": asset_symbol,
        "event_type": item["event_type"],
        "quantity_reference": _decimal_text(
            item["quantity_reference"]
        ),
        "gross_amount": _decimal_text(item["gross_amount"]),
        "net_amount": _decimal_text(item["net_amount"]),
        "expected_payment_date": item["expected_payment_date"],
        "occurrence": occurrence,
    }

    payload = json.dumps(
        identity,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_or_create_account(
    con: sqlite3.Connection,
    account_code: str,
) -> int:
    con.execute(
        """
        INSERT OR IGNORE INTO portfolio_accounts (
            code, name, broker, market, base_currency
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            account_code,
            f"XP Investimentos - Conta {account_code}",
            BROKER,
            MARKET,
            CURRENCY,
        ),
    )

    row = con.execute(
        """
        SELECT id, broker, market, base_currency
        FROM portfolio_accounts
        WHERE code = ?
        """,
        (account_code,),
    ).fetchone()

    if row is None:
        raise RuntimeError("Não foi possível localizar a conta XP.")

    if (
        row["broker"] != BROKER
        or row["market"] != MARKET
        or row["base_currency"] != CURRENCY
    ):
        raise ValueError(
            "A conta já existe, mas possui corretora, mercado "
            "ou moeda-base incompatível."
        )

    return int(row["id"])


def _get_or_create_asset(
    con: sqlite3.Connection,
    position: dict[str, Any],
) -> int:
    symbol = position["symbol"]
    asset_type = position["type"]
    name = position["name"]

    con.execute(
        """
        INSERT OR IGNORE INTO portfolio_assets (
            market, symbol, name, asset_type, quote_currency
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (MARKET, symbol, name, asset_type, CURRENCY),
    )

    row = con.execute(
        """
        SELECT id, asset_type, quote_currency
        FROM portfolio_assets
        WHERE market = ? AND symbol = ?
        """,
        (MARKET, symbol),
    ).fetchone()

    if row is None:
        raise RuntimeError(f"Não foi possível cadastrar o ativo {symbol}.")

    if (
        row["asset_type"] != asset_type
        or row["quote_currency"] != CURRENCY
    ):
        raise ValueError(
            f"Cadastro incompatível para o ativo {symbol}: "
            "tipo ou moeda divergente."
        )

    return int(row["id"])


def import_xp_data(
    data: dict[str, Any],
    db_path: str | None = None,
) -> dict[str, Any]:
    """
    Importa uma fotografia da carteira XP em uma única transação.

    Não cria transações históricas de compra ou venda.
    """

    if not all(data["checks"].values()):
        raise ValueError(
            "Importação bloqueada: existem validações do parser que falharam."
        )

    account_code = data["account_code"]

    if account_code != "7737516":
        raise ValueError(
            f"Conta XP não autorizada para este importador: {account_code}"
        )

    snapshot_date = data["snapshot_date"]
    file_hash = data["sha256"]

    con = connect(db_path)

    try:
        con.execute("BEGIN IMMEDIATE")

        account_id = _get_or_create_account(con, account_code)

        # Deduplicação do arquivo completo.
        existing = con.execute(
            """
            SELECT id, status
            FROM portfolio_imports
            WHERE account_id = ? AND file_sha256 = ?
            """,
            (account_id, file_hash),
        ).fetchone()

        if existing is not None:
            con.rollback()

            if existing["status"] == "IMPORTED":
                return {
                    "already_imported": True,
                    "import_id": int(existing["id"]),
                    "account_id": account_id,
                }

            raise ValueError(
                "Já existe um registro deste arquivo com status "
                f"{existing['status']!r}. Verifique antes de prosseguir."
            )

        # Não permite dois snapshots XP para a mesma data.
        existing_snapshot = con.execute(
            """
            SELECT id
            FROM portfolio_snapshots
            WHERE account_id = ?
              AND snapshot_date = ?
              AND currency = ?
            """,
            (account_id, snapshot_date, CURRENCY),
        ).fetchone()

        if existing_snapshot is not None:
            raise ValueError(
                "Já existe um snapshot desta conta para "
                f"{snapshot_date}. Nenhum dado foi gravado."
            )

        existing_positions = con.execute(
            """
            SELECT id
            FROM portfolio_positions
            WHERE account_id = ?
              AND snapshot_date = ?
              AND source = ?
            LIMIT 1
            """,
            (account_id, snapshot_date, SOURCE),
        ).fetchone()

        if existing_positions is not None:
            raise ValueError(
                "Já existem posições importadas da XP para "
                f"{snapshot_date}. Nenhum dado foi gravado."
            )

        # Registro do processo de importação.
        cursor = con.execute(
            """
            INSERT INTO portfolio_imports (
                account_id,
                source_type,
                filename,
                file_sha256,
                snapshot_date,
                status,
                row_count
            )
            VALUES (?, 'XP_XLSX', ?, ?, ?, 'PENDING', 0)
            """,
            (
                account_id,
                data["filename"],
                file_hash,
                snapshot_date,
            ),
        )

        import_id = int(cursor.lastrowid)

        # Cadastro dos ativos e gravação das posições.
        for position in data["positions"]:
            asset_id = _get_or_create_asset(con, position)

            con.execute(
                """
                INSERT INTO portfolio_positions (
                    account_id,
                    asset_id,
                    import_id,
                    snapshot_date,
                    quantity,
                    average_cost,
                    invested_amount,
                    market_price,
                    market_value,
                    net_liquidation_value,
                    currency,
                    source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    asset_id,
                    import_id,
                    snapshot_date,
                    _as_float(position["quantity"]),
                    _as_float(position["average_cost"]),
                    _as_float(position["invested_amount"]),
                    _as_float(position["market_price"]),
                    _as_float(position["market_value"]),
                    _as_float(position["net_liquidation_value"]),
                    CURRENCY,
                    SOURCE,
                ),
            )

        # Cadastro de ativos e gravação dos proventos.
        incomes_inserted = 0
        incomes_duplicated = 0
        income_occurrences: dict[str, int] = {}

        for item in data["incomes"]:
            symbol = item["symbol"]

            # O ativo pode não estar entre as posições atuais,
            # como ocorre com JPPA11.
            asset_data = {
                "symbol": symbol,
                "name": symbol,
                "type": (
                    "BDR" if symbol.endswith("34")
                    else "FII" if symbol.endswith("11")
                    else "STOCK"
                ),
            }

            asset_id = _get_or_create_asset(con, asset_data)

            base_key = _income_dedupe_key(
                account_id,
                symbol,
                item,
                occurrence=0,
            )

            occurrence = income_occurrences.get(base_key, 0) + 1
            income_occurrences[base_key] = occurrence

            dedupe_key = _income_dedupe_key(
                account_id,
                symbol,
                item,
                occurrence=occurrence,
            )

            cursor = con.execute(
                """
                INSERT OR IGNORE INTO portfolio_income (
                    account_id,
                    asset_id,
                    import_id,
                    dedupe_key,
                    event_type,
                    gross_amount,
                    net_amount,
                    currency,
                    status,
                    expected_payment_date,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (
                    account_id,
                    asset_id,
                    import_id,
                    dedupe_key,
                    item["event_type"],
                    _as_float(item["gross_amount"]),
                    _as_float(item["net_amount"]),
                    CURRENCY,
                    item["expected_payment_date"],
                    (
                        f"Importado da XP; "
                        f"quantidade de referência: "
                        f"{_decimal_text(item['quantity_reference'])}"
                    ),
                ),
            )

            if cursor.rowcount == 1:
                incomes_inserted += 1
            else:
                incomes_duplicated += 1

        # Fotografia consolidada.
        metadata = {
            "source": "XP_XLSX",
            "filename": data["filename"],
            "sha256": file_hash,
            "positions_count": len(data["positions"]),
            "incomes_count": len(data["incomes"]),
            "incomes_inserted": incomes_inserted,
            "incomes_duplicated": incomes_duplicated,
            "positions_market_value": str(data["position_total"]),
            "pending_income_gross": str(data["income_gross_total"]),
            "pending_income_net": str(data["income_net_total"]),
            "xp_reported_total": str(data["xp_total"]),
        }

        con.execute(
            """
            INSERT INTO portfolio_snapshots (
                account_id,
                snapshot_date,
                total_market_value,
                available_cash,
                pending_income,
                currency,
                details_json
            )
            VALUES (?, ?, ?, 0, ?, ?, ?)
            """,
            (
                account_id,
                snapshot_date,
                float(data["position_total"]),
                float(data["income_gross_total"]),
                CURRENCY,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )

        row_count = len(data["positions"]) + len(data["incomes"])

        con.execute(
            """
            UPDATE portfolio_imports
            SET status = 'IMPORTED',
                row_count = ?,
                imported_at = CURRENT_TIMESTAMP,
                metadata_json = ?
            WHERE id = ?
            """,
            (
                row_count,
                json.dumps(metadata, ensure_ascii=False),
                import_id,
            ),
        )

        con.commit()

        return {
            "already_imported": False,
            "import_id": import_id,
            "account_id": account_id,
            "positions_inserted": len(data["positions"]),
            "incomes_inserted": incomes_inserted,
            "incomes_duplicated": incomes_duplicated,
            "snapshot_date": snapshot_date,
        }

    except Exception:
        if con.in_transaction:
            con.rollback()
        raise

    finally:
        con.close()

