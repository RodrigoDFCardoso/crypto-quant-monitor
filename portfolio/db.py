"""Conexões SQLite compartilhadas pelo módulo de carteira.

O módulo usa o mesmo banco do scanner, sem criar um banco separado.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "crypto_market.db"


def get_db_path(path: str | Path | None = None) -> Path:
    """Resolve o caminho explícito, variável de ambiente ou banco padrão."""
    if path is not None:
        return Path(path).expanduser().resolve()

    configured = os.getenv("CRYPTO_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()

    return DEFAULT_DB_PATH.resolve()


def connect(
    path: str | Path | None = None,
    *,
    timeout: float = 30.0,
) -> sqlite3.Connection:
    """Abre o SQLite com FK, WAL e espera para contenção de escrita."""
    db_path = get_db_path(path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(db_path), timeout=timeout)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    if str(db_path) != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL")

    return connection
