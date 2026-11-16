"""Migrações incrementais e idempotentes do banco Crypto Quant Monitor.

Uso: python -m portfolio.migrate [--db CAMINHO] [--status]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from portfolio.db import connect, get_db_path

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
MIGRATIONS = (
    (1, "schema inicial da carteira"),
    (2, "campos complementares de posição"),
)


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()


def _applied_versions(connection: sqlite3.Connection) -> set[int]:
    rows = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {int(row[0]) for row in rows}


def _apply_initial_schema(connection: sqlite3.Connection) -> None:
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    # executescript faz commit implícito; BEGIN/COMMIT explícitos garantem
    # que DDL e registro da migração sejam aplicados como uma unidade.
    script = (
        "BEGIN IMMEDIATE;\n"
        + schema
        + "\nINSERT INTO schema_migrations(version, description) "
          "VALUES (1, 'schema inicial da carteira');\nCOMMIT;"
    )
    try:
        connection.executescript(script)
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row[1]) for row in rows}


def _apply_position_columns(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "portfolio_positions")
    if not columns:
        raise RuntimeError(
            "portfolio_positions não existe após a migração inicial."
        )

    connection.execute("BEGIN IMMEDIATE")
    try:
        if "invested_amount" not in columns:
            connection.execute(
                "ALTER TABLE portfolio_positions ADD COLUMN invested_amount REAL"
            )
        if "net_liquidation_value" not in columns:
            connection.execute(
                "ALTER TABLE portfolio_positions "
                "ADD COLUMN net_liquidation_value REAL"
            )
        connection.execute(
            "INSERT INTO schema_migrations(version, description) VALUES (?, ?)",
            (2, "campos complementares de posição"),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def migrate_database(path: str | Path | None = None) -> list[tuple[int, str]]:
    """Aplica somente migrações pendentes e devolve as recém aplicadas."""
    connection = connect(path)
    applied_now: list[tuple[int, str]] = []
    try:
        _ensure_migration_table(connection)
        applied = _applied_versions(connection)

        if 1 not in applied:
            _apply_initial_schema(connection)
            applied_now.append(MIGRATIONS[0])
            applied.add(1)

        if 2 not in applied:
            _apply_position_columns(connection)
            applied_now.append(MIGRATIONS[1])

        return applied_now
    finally:
        connection.close()


def migration_status(path: str | Path | None = None) -> list[tuple[int, str, str | None]]:
    connection = connect(path)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not exists:
            return []
        rows = connection.execute(
            "SELECT version, description, applied_at "
            "FROM schema_migrations ORDER BY version"
        ).fetchall()
        return [(int(r[0]), str(r[1]), r[2]) for r in rows]
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra o banco do Crypto Quant Monitor")
    parser.add_argument("--db", type=Path, default=None, help="Caminho do SQLite")
    parser.add_argument(
        "--status", action="store_true", help="Mostra migrações aplicadas sem migrar"
    )
    args = parser.parse_args()
    db_path = get_db_path(args.db)

    if args.status:
        rows = migration_status(db_path)
        print(f"Banco: {db_path}")
        if not rows:
            print("Nenhuma migração registrada.")
        for version, description, applied_at in rows:
            print(f"[{version:03}] {description} — {applied_at}")
        return 0

    applied = migrate_database(db_path)
    print(f"Banco: {db_path}")
    if applied:
        for version, description in applied:
            print(f"[OK] Migração {version:03}: {description}")
    else:
        print("[OK] Banco já está atualizado; nenhuma alteração necessária.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
