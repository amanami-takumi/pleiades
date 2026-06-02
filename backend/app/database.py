from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/usr/src/data/pleiades.sqlite3"))


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS symbols (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ticker TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              asset_type TEXT NOT NULL DEFAULT 'stock',
              tag TEXT NOT NULL DEFAULT 'ウォッチリスト',
              display_order INTEGER NOT NULL DEFAULT 0,
              currency TEXT,
              exchange TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS prices (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
              date TEXT NOT NULL,
              open REAL,
              high REAL,
              low REAL,
              close REAL,
              adj_close REAL,
              volume INTEGER,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(symbol_id, date)
            );

            CREATE TABLE IF NOT EXISTS fundamentals (
              symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
              per REAL,
              pbr REAL,
              roe REAL,
              market_cap REAL,
              dividend_yield REAL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS app_state (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS refresh_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              symbol_id INTEGER REFERENCES symbols(id) ON DELETE SET NULL,
              ticker TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              error TEXT,
              queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              started_at TEXT,
              finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS purchases (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
              purchased_at TEXT NOT NULL,
              amount REAL NOT NULL,
              quantity REAL NOT NULL,
              note TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        ensure_column(db, "symbols", "tag", "TEXT NOT NULL DEFAULT 'ウォッチリスト'")
        ensure_column(db, "symbols", "display_order", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "symbols", "last_error", "TEXT")
        ensure_column(db, "symbols", "last_refreshed_at", "TEXT")
        ensure_column(db, "refresh_jobs", "cancel_requested", "INTEGER NOT NULL DEFAULT 0")
        db.execute("UPDATE symbols SET display_order = id WHERE display_order = 0")


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def seed_defaults() -> None:
    defaults = [
        ("^GSPC", "S&P 500", "index"),
        ("^IXIC", "NASDAQ Composite", "index"),
        ("^DJI", "Dow Jones Industrial Average", "index"),
        ("^N225", "Nikkei 225", "index"),
        ("AAPL", "Apple", "stock"),
        ("MSFT", "Microsoft", "stock"),
        ("7203.T", "Toyota Motor", "stock"),
    ]
    with get_db() as db:
        for ticker, name, asset_type in defaults:
            db.execute(
                """
                INSERT OR IGNORE INTO symbols (ticker, name, asset_type, display_order)
                VALUES (?, ?, ?, COALESCE((SELECT MAX(display_order) + 10 FROM symbols), 10))
                """,
                (ticker, name, asset_type),
            )
