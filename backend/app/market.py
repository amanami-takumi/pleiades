from __future__ import annotations

import math
import os
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from typing import Callable, Iterable, TypeVar

import pandas as pd
import yfinance as yf

from .fund_sources import FundHistory, fetch_yahoo_finance_fund_history


RANGE_TO_DAYS = {
    "1w": 7,
    "1m": 31,
    "3m": 93,
    "1y": 366,
    "2y": 732,
    "3y": 1098,
    "5y": 1830,
}

YFINANCE_REQUEST_INTERVAL_SECONDS = float(os.getenv("YFINANCE_REQUEST_INTERVAL_SECONDS", "2"))
YFINANCE_SYMBOL_INTERVAL_SECONDS = float(os.getenv("YFINANCE_SYMBOL_INTERVAL_SECONDS", "5"))
YFINANCE_RETRY_COUNT = int(os.getenv("YFINANCE_RETRY_COUNT", "2"))
YFINANCE_RATE_LIMIT_BACKOFF_SECONDS = float(os.getenv("YFINANCE_RATE_LIMIT_BACKOFF_SECONDS", "60"))

RATE_LIMIT_MARKERS = (
    "too many requests",
    "rate limited",
    "rate limit",
    "429",
)

T = TypeVar("T")


def _finite(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _int_or_none(value: object) -> int | None:
    number = _finite(value)
    return int(number) if number is not None else None


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def is_japanese_fund_code(ticker: str) -> bool:
    return bool(ticker) and "." not in ticker and "^" not in ticker and len(ticker) == 8 and ticker.isalnum()


def is_rate_limit_error(error: BaseException) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in RATE_LIMIT_MARKERS)


def call_yfinance(operation: Callable[[], T]) -> T:
    last_error: BaseException | None = None
    for attempt in range(YFINANCE_RETRY_COUNT + 1):
        if attempt > 0:
            time.sleep(YFINANCE_RATE_LIMIT_BACKOFF_SECONDS * attempt)
        else:
            time.sleep(YFINANCE_REQUEST_INTERVAL_SECONDS)

        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if not is_rate_limit_error(exc) or attempt >= YFINANCE_RETRY_COUNT:
                raise

    raise last_error or RuntimeError("yfinance request failed")


def store_fund_history(db: sqlite3.Connection, symbol_id: int, ticker: str, history: FundHistory) -> None:
    for point in history.points:
        db.execute(
            """
            INSERT INTO prices (symbol_id, date, open, high, low, close, adj_close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol_id, date) DO UPDATE SET
              open = excluded.open,
              high = excluded.high,
              low = excluded.low,
              close = excluded.close,
              adj_close = excluded.adj_close,
              volume = excluded.volume
            """,
            (
                symbol_id,
                point.date,
                point.price,
                point.price,
                point.price,
                point.price,
                point.price,
                point.net_assets_million,
            ),
        )
    db.execute(
        """
        UPDATE symbols
        SET
          name = ?,
          currency = 'JPY',
          exchange = ?,
          last_error = NULL,
          last_refreshed_at = CURRENT_TIMESTAMP,
          updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (history.name, history.source, symbol_id),
    )


def fetch_and_store_fund_fallback(db: sqlite3.Connection, symbol_id: int, ticker: str) -> None:
    history = fetch_yahoo_finance_fund_history(ticker)
    store_fund_history(db, symbol_id, ticker, history)


def fetch_and_store_symbol(
    db: sqlite3.Connection,
    symbol_id: int,
    ticker: str,
    asset_type: str,
    period: str = "5y",
) -> None:
    if asset_type == "fund" and is_japanese_fund_code(ticker):
        fetch_and_store_fund_fallback(db, symbol_id, ticker)
        return

    stock = yf.Ticker(ticker)
    yfinance_error: BaseException | None = None
    try:
        history = call_yfinance(lambda: stock.history(period=period, interval="1d", auto_adjust=False))
    except Exception as exc:
        history = pd.DataFrame()
        yfinance_error = exc

    if not isinstance(history, pd.DataFrame) or history.empty:
        if asset_type == "fund":
            fetch_and_store_fund_fallback(db, symbol_id, ticker)
            return
        suffix = f" yfinance error: {yfinance_error}" if yfinance_error else ""
        raise LookupError(
            f"{ticker}: yfinance returned no daily price history. Check the ticker symbol or Yahoo Finance support.{suffix}"
        )

    for index, row in history.iterrows():
        date = index.date().isoformat()
        db.execute(
            """
            INSERT INTO prices (symbol_id, date, open, high, low, close, adj_close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol_id, date) DO UPDATE SET
              open = excluded.open,
              high = excluded.high,
              low = excluded.low,
              close = excluded.close,
              adj_close = excluded.adj_close,
              volume = excluded.volume
            """,
            (
                symbol_id,
                date,
                _finite(row.get("Open")),
                _finite(row.get("High")),
                _finite(row.get("Low")),
                _finite(row.get("Close")),
                _finite(row.get("Adj Close")),
                _int_or_none(row.get("Volume")),
            )
        )

    info_error: str | None = None
    try:
        info = call_yfinance(stock.get_info)
    except Exception as exc:
        info = {}
        info_error = str(exc) or exc.__class__.__name__
    name = info.get("shortName") or info.get("longName") or ticker

    db.execute(
        """
        UPDATE symbols
        SET name = ?, currency = ?, exchange = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (name, info.get("currency"), info.get("exchange"), symbol_id),
    )

    db.execute(
        """
        INSERT INTO fundamentals (symbol_id, per, pbr, roe, market_cap, dividend_yield, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(symbol_id) DO UPDATE SET
          per = excluded.per,
          pbr = excluded.pbr,
          roe = excluded.roe,
          market_cap = excluded.market_cap,
          dividend_yield = excluded.dividend_yield,
          updated_at = CURRENT_TIMESTAMP
        """,
        (
            symbol_id,
            _finite(info.get("trailingPE")),
            _finite(info.get("priceToBook")),
            _finite(info.get("returnOnEquity")),
            _finite(info.get("marketCap")),
            _finite(info.get("dividendYield")),
        ),
    )
    db.execute(
        """
        UPDATE symbols
        SET last_error = NULL, last_refreshed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (symbol_id,),
    )
    if info_error:
        raise RuntimeError(f"{ticker}: price history updated, but yfinance info failed: {info_error}")


def refresh_symbols(db: sqlite3.Connection, symbol_ids: Iterable[int] | None = None) -> tuple[list[str], dict[str, str]]:
    params: tuple[object, ...] = tuple(symbol_ids or [])
    where = f"WHERE id IN ({','.join('?' for _ in params)})" if params else ""
    rows = db.execute(f"SELECT id, ticker, asset_type FROM symbols {where} ORDER BY id", params).fetchall()
    refreshed: list[str] = []
    errors: dict[str, str] = {}

    for row in rows:
        ticker = row["ticker"]
        try:
            fetch_and_store_symbol(db, row["id"], ticker, row["asset_type"], period="5y")
            refreshed.append(ticker)
        except Exception as exc:  # yfinance errors are intentionally isolated per symbol.
            message = str(exc) or exc.__class__.__name__
            errors[ticker] = message
            db.execute(
                """
                UPDATE symbols
                SET last_error = ?, last_refreshed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (message, row["id"]),
            )
        time.sleep(YFINANCE_SYMBOL_INTERVAL_SECONDS)
    db.execute(
        """
        INSERT INTO app_state (key, value, updated_at)
        VALUES ('last_refresh', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """,
        (datetime.now(UTC).isoformat(),),
    )
    return refreshed, errors


def refresh_symbol_row(db: sqlite3.Connection, symbol_id: int) -> None:
    row = db.execute("SELECT id, ticker, asset_type FROM symbols WHERE id = ?", (symbol_id,)).fetchone()
    if row is None:
        raise LookupError(f"Symbol {symbol_id} not found")
    fetch_and_store_symbol(db, row["id"], row["ticker"], row["asset_type"], period="5y")


def refresh_if_stale(db: sqlite3.Connection) -> tuple[list[str], dict[str, str]]:
    row = db.execute("SELECT value FROM app_state WHERE key = 'last_refresh'").fetchone()
    if row:
        last_refresh = datetime.fromisoformat(row["value"])
        if datetime.now(UTC) - last_refresh < timedelta(hours=20):
            return [], {}
    return refresh_symbols(db)
