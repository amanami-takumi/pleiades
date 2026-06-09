from __future__ import annotations

import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from bs4 import BeautifulSoup

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

MARKET_REQUEST_INTERVAL_SECONDS = float(os.getenv("MARKET_REQUEST_INTERVAL_SECONDS", "2"))
MARKET_SYMBOL_INTERVAL_SECONDS = float(os.getenv("MARKET_SYMBOL_INTERVAL_SECONDS", "5"))
MARKET_RETRY_COUNT = int(os.getenv("MARKET_RETRY_COUNT", "2"))
MARKET_RATE_LIMIT_BACKOFF_SECONDS = float(os.getenv("MARKET_RATE_LIMIT_BACKOFF_SECONDS", "60"))
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
YAHOO_US_QUOTE_PAGE_URL = "https://finance.yahoo.com/quote/{ticker}"
YAHOO_JP_QUOTE_PAGE_URL = "https://finance.yahoo.co.jp/quote/{ticker}"
YAHOO_FINANCE_HEADERS = {
    "User-Agent": "Mozilla/5.0 Pleiades/0.1 (+private-home-app)",
    "Accept": "application/json",
}
YAHOO_FINANCE_HTML_HEADERS = {
    "User-Agent": YAHOO_FINANCE_HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml",
}

RATE_LIMIT_MARKERS = (
    "too many requests",
    "rate limited",
    "rate limit",
    "429",
)


@dataclass(frozen=True)
class MarketHistoryPoint:
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adj_close: float | None
    volume: int | None


@dataclass(frozen=True)
class MarketHistory:
    name: str
    currency: str | None
    exchange: str | None
    per: float | None
    pbr: float | None
    roe: float | None
    market_cap: float | None
    dividend_yield: float | None
    points: list[MarketHistoryPoint]


@dataclass(frozen=True)
class MarketFundamentals:
    name: str | None = None
    per: float | None = None
    pbr: float | None = None
    roe: float | None = None
    market_cap: float | None = None
    dividend_yield: float | None = None


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


def call_market_source(operation):
    last_error: BaseException | None = None
    for attempt in range(MARKET_RETRY_COUNT + 1):
        if attempt > 0:
            time.sleep(MARKET_RATE_LIMIT_BACKOFF_SECONDS * attempt)
        else:
            time.sleep(MARKET_REQUEST_INTERVAL_SECONDS)

        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if not is_rate_limit_error(exc) or attempt >= MARKET_RETRY_COUNT:
                raise

    raise last_error or RuntimeError("market data request failed")


def fetch_yahoo_chart_history(ticker: str, period: str = "5y") -> MarketHistory:
    response = call_market_source(lambda: get_json_response(YAHOO_CHART_URL.format(ticker=ticker), {
        "range": period,
        "interval": "1d",
        "includePrePost": "false",
        "events": "div,splits",
    }))
    payload = response.json()
    chart = payload.get("chart", {})
    errors = chart.get("error")
    if errors:
        description = errors.get("description") or errors.get("code") or errors
        raise LookupError(f"{ticker}: Yahoo Finance chart returned an error: {description}")

    results = chart.get("result") or []
    if not results:
        raise LookupError(f"{ticker}: Yahoo Finance chart returned no result.")

    result = results[0]
    meta = result.get("meta") or {}
    timezone = parse_exchange_timezone(meta)
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0]
    adjclose = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []

    points: list[MarketHistoryPoint] = []
    for index, timestamp in enumerate(timestamps):
        close = _finite(_list_value(quote.get("close"), index))
        if close is None:
            continue
        points.append(
            MarketHistoryPoint(
                date=datetime.fromtimestamp(int(timestamp), timezone).date().isoformat(),
                open=_finite(_list_value(quote.get("open"), index)),
                high=_finite(_list_value(quote.get("high"), index)),
                low=_finite(_list_value(quote.get("low"), index)),
                close=close,
                adj_close=_finite(_list_value(adjclose, index)) or close,
                volume=_int_or_none(_list_value(quote.get("volume"), index)),
            )
        )

    if not points:
        raise LookupError(f"{ticker}: Yahoo Finance chart returned no daily price history.")

    quote_summary = fetch_yahoo_quote_summary(ticker)
    fundamentals = fetch_market_fundamentals(ticker, quote_summary)
    return MarketHistory(
        name=fundamentals.name or meta.get("shortName") or meta.get("longName") or ticker,
        currency=quote_summary.get("currency") or meta.get("currency"),
        exchange=(
            quote_summary.get("fullExchangeName")
            or quote_summary.get("exchange")
            or meta.get("exchangeName")
            or meta.get("fullExchangeName")
            or meta.get("exchange")
        ),
        per=fundamentals.per,
        pbr=fundamentals.pbr,
        roe=fundamentals.roe,
        market_cap=fundamentals.market_cap,
        dividend_yield=fundamentals.dividend_yield,
        points=points,
    )


def get_json_response(url: str, params: dict[str, object]) -> requests.Response:
    response = requests.get(url, params=params, headers=YAHOO_FINANCE_HEADERS, timeout=20)
    response.raise_for_status()
    return response


def parse_exchange_timezone(meta: dict[str, object]) -> ZoneInfo:
    timezone_name = meta.get("exchangeTimezoneName")
    if isinstance(timezone_name, str):
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            pass
    return ZoneInfo("UTC")


def fetch_yahoo_quote_summary(ticker: str) -> dict[str, object]:
    try:
        response = call_market_source(lambda: get_json_response(YAHOO_QUOTE_URL, {"symbols": ticker}))
        result = response.json().get("quoteResponse", {}).get("result") or []
        if isinstance(result, list) and result:
            return result[0]
    except Exception:
        return {}
    return {}


def fetch_market_fundamentals(ticker: str, quote_summary: dict[str, object]) -> MarketFundamentals:
    scraped = fetch_scraped_fundamentals(ticker)
    return MarketFundamentals(
        name=scraped.name,
        per=_finite(quote_summary.get("trailingPE")) or scraped.per,
        pbr=_finite(quote_summary.get("priceToBook")) or scraped.pbr,
        roe=_finite(quote_summary.get("returnOnEquity")) or scraped.roe,
        market_cap=_finite(quote_summary.get("marketCap")) or scraped.market_cap,
        dividend_yield=normalize_dividend_yield(quote_summary.get("dividendYield")) or scraped.dividend_yield,
    )


def fetch_scraped_fundamentals(ticker: str) -> MarketFundamentals:
    if ticker.endswith(".T"):
        return fetch_yahoo_japan_stock_fundamentals(ticker)
    return fetch_yahoo_us_stock_fundamentals(ticker)


def fetch_yahoo_us_stock_fundamentals(ticker: str) -> MarketFundamentals:
    try:
        response = call_market_source(
            lambda: get_html_response(YAHOO_US_QUOTE_PAGE_URL.format(ticker=ticker), {"p": ticker})
        )
    except Exception:
        return MarketFundamentals()

    html = response.text
    return MarketFundamentals(
        name=extract_yahoo_us_stock_name(html, ticker),
        per=extract_yahoo_us_raw_metric(html, "trailingPE"),
        pbr=extract_yahoo_us_raw_metric(html, "priceToBook"),
        roe=extract_yahoo_us_ratio_metric(html, "returnOnEquity"),
        market_cap=extract_yahoo_us_raw_metric(html, "marketCap"),
        dividend_yield=(
            extract_yahoo_us_percent_metric(html, "dividendYield")
            or extract_yahoo_us_percent_metric(html, "trailingAnnualDividendYield")
        ),
    )


def fetch_yahoo_japan_stock_fundamentals(ticker: str) -> MarketFundamentals:
    try:
        response = call_market_source(lambda: get_html_response(YAHOO_JP_QUOTE_PAGE_URL.format(ticker=ticker), {}))
    except Exception:
        return MarketFundamentals()

    soup = BeautifulSoup(response.text, "html.parser")
    return MarketFundamentals(
        name=extract_yahoo_japan_stock_name(soup, ticker),
        per=extract_yahoo_japan_labeled_number(soup, "PER"),
        pbr=extract_yahoo_japan_labeled_number(soup, "PBR"),
        roe=normalize_labeled_percent(extract_yahoo_japan_labeled_number(soup, "ROE")),
        dividend_yield=extract_yahoo_japan_labeled_number(soup, "配当利回り"),
    )


def get_html_response(url: str, params: dict[str, object]) -> requests.Response:
    response = requests.get(url, params=params, headers=YAHOO_FINANCE_HTML_HEADERS, timeout=20)
    response.raise_for_status()
    return response


def extract_yahoo_us_stock_name(html: str, ticker: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    title = parse_meta_or_title(soup)
    if title:
        name = title.split(" Stock Price", 1)[0].strip()
        name = re.sub(rf"\s*\({re.escape(ticker)}\)\s*$", "", name).strip()
        if name and name.upper() != ticker.upper():
            return name
    return None


def extract_yahoo_japan_stock_name(soup: BeautifulSoup, ticker: str) -> str | None:
    title = parse_meta_or_title(soup)
    if title:
        name = title.split("【", 1)[0].split("：", 1)[0].strip()
        if name and name.upper() != ticker.upper():
            return name
    heading = soup.find("h1")
    if heading:
        name = heading.get_text("", strip=True).split("の株価", 1)[0].strip()
        if name and name.upper() != ticker.upper():
            return name
    return None


def parse_meta_or_title(soup: BeautifulSoup) -> str | None:
    for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
        tag = soup.find("meta", attrs=attrs)
        content = tag.get("content") if tag else None
        if content:
            return content.strip()
    if soup.title:
        return soup.title.get_text("", strip=True)
    return None


def extract_yahoo_us_raw_metric(html: str, field: str) -> float | None:
    raw = extract_yahoo_us_metric_raw_text(html, field)
    if raw is not None:
        return parse_metric_number(raw)
    match = re.search(rf'data-value="([^"]+)"[^>]*data-field="{re.escape(field)}"', html)
    if match:
        return parse_metric_number(match.group(1))
    return None


def extract_yahoo_us_percent_metric(html: str, field: str) -> float | None:
    raw, formatted = extract_yahoo_us_metric_raw_and_fmt(html, field)
    if formatted and "%" in formatted:
        return parse_metric_number(formatted)
    return normalize_dividend_yield(raw)


def extract_yahoo_us_ratio_metric(html: str, field: str) -> float | None:
    raw, formatted = extract_yahoo_us_metric_raw_and_fmt(html, field)
    if raw is not None:
        return _finite(raw)
    if formatted and "%" in formatted:
        parsed = parse_metric_number(formatted)
        return parsed / 100 if parsed is not None else None
    return None


def extract_yahoo_us_metric_raw_text(html: str, field: str) -> str | None:
    raw, _ = extract_yahoo_us_metric_raw_and_fmt(html, field)
    return raw


def extract_yahoo_us_metric_raw_and_fmt(html: str, field: str) -> tuple[str | None, str | None]:
    escaped_pattern = re.compile(
        rf'\\"{re.escape(field)}\\":\{{\\"raw\\":([^,}}]+),\\"fmt\\":\\"([^\\"]*)\\"'
    )
    match = escaped_pattern.search(html)
    if match:
        return match.group(1), match.group(2)

    plain_pattern = re.compile(rf'"{re.escape(field)}":\{{"raw":([^,}}]+),"fmt":"([^"]*)"')
    match = plain_pattern.search(html)
    if match:
        return match.group(1), match.group(2)

    return None, None


def extract_yahoo_japan_labeled_number(soup: BeautifulSoup, label: str) -> float | None:
    for term in soup.find_all("dt"):
        if label not in term.get_text("", strip=True):
            continue
        description = term.find_next_sibling("dd")
        if description is None:
            continue
        value = description.find(class_=re.compile(r"DataListItem__value"))
        if value is not None:
            parsed = parse_metric_number(value.get_text("", strip=True))
            if parsed is not None:
                return parsed
        parsed = parse_metric_number(description.get_text("", strip=True))
        if parsed is not None:
            return parsed
    return None


def parse_metric_number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    text = re.sub(r"^[^\d.+-]+", "", text)
    text = re.sub(r"[^\d.。+-].*$", "", text).replace("。", ".")
    if text in {"", "-", "--"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def normalize_dividend_yield(value: object) -> float | None:
    number = parse_metric_number(value)
    if number is None:
        return None
    return number * 100 if 0 < number <= 1 else number


def normalize_labeled_percent(value: object) -> float | None:
    number = parse_metric_number(value)
    if number is None:
        return None
    return number / 100


def _list_value(values: object, index: int) -> object | None:
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


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

    try:
        history = fetch_yahoo_chart_history(ticker, period=period)
    except Exception:
        if asset_type == "fund":
            fetch_and_store_fund_fallback(db, symbol_id, ticker)
            return
        raise

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
                point.open,
                point.high,
                point.low,
                point.close,
                point.adj_close,
                point.volume,
            )
        )

    db.execute(
        """
        UPDATE symbols
        SET name = ?, currency = ?, exchange = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (history.name, history.currency, history.exchange, symbol_id),
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
            history.per,
            history.pbr,
            history.roe,
            history.market_cap,
            history.dividend_yield,
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
        except Exception as exc:
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
        time.sleep(MARKET_SYMBOL_INTERVAL_SECONDS)
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
