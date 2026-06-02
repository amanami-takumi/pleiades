from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json

import requests
from bs4 import BeautifulSoup


YAHOO_FINANCE_HEADERS = {
    "User-Agent": "Mozilla/5.0 Pleiades/0.1 (+private-home-app)"
}
YAHOO_FINANCE_HISTORY_SIZE = 2000


@dataclass(frozen=True)
class FundHistoryPoint:
    date: str
    price: float
    net_assets_million: int | None


@dataclass(frozen=True)
class FundHistory:
    name: str
    source: str
    points: list[FundHistoryPoint]


def fetch_yahoo_finance_fund_history(ticker: str) -> FundHistory:
    try:
        return fetch_yahoo_finance_fund_history_api(ticker)
    except Exception:
        return fetch_yahoo_finance_fund_history_html(ticker)


def fetch_yahoo_finance_fund_history_api(ticker: str, years: int = 5) -> FundHistory:
    page_url = f"https://finance.yahoo.co.jp/quote/{ticker}/history"
    page_response = requests.get(page_url, headers=YAHOO_FINANCE_HEADERS, timeout=20)
    page_response.raise_for_status()

    token = extract_jwt_token(page_response.text)
    to_date = datetime.now(UTC).date()
    from_date = to_date - timedelta(days=366 * years)
    history_url = f"https://finance.yahoo.co.jp/bff-pc/v1/main/fund/price/history/{ticker}"
    headers = {
        **YAHOO_FINANCE_HEADERS,
        "Referer": page_url,
        "jwt-token": token,
    }

    points: list[FundHistoryPoint] = []
    page = 1
    while True:
        response = requests.get(
            history_url,
            params={
                "displayedMaxPage": 5,
                "fromDate": from_date.strftime("%Y%m%d"),
                "toDate": to_date.strftime("%Y%m%d"),
                "page": page,
                "size": YAHOO_FINANCE_HISTORY_SIZE,
                "timeFrame": "daily",
            },
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        for row in payload.get("histories", []):
            point = parse_history_row(row)
            if point:
                points.append(point)

        paging = payload.get("paging", {})
        if not paging.get("hasNext") or page >= int(paging.get("totalPage", page)):
            break
        page += 1

    if not points:
        raise LookupError(f"{ticker}: Yahoo Finance Japan API returned no fund history rows.")

    soup = BeautifulSoup(page_response.text, "html.parser")
    return FundHistory(
        name=parse_name(soup, ticker),
        source="Yahoo Finance Japan BFF",
        points=sorted(points, key=lambda point: point.date),
    )


def fetch_yahoo_finance_fund_history_html(ticker: str) -> FundHistory:
    url = f"https://finance.yahoo.co.jp/quote/{ticker}/history"
    response = requests.get(url, headers=YAHOO_FINANCE_HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.find_all("tr")
    points: list[FundHistoryPoint] = []
    for row in rows:
        cells = [cell.get_text("", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) < 4 or cells[0] == "日付":
            continue
        date = parse_japanese_date(cells[0])
        price = parse_number(cells[1])
        net_assets = parse_int(cells[3])
        if date and price is not None:
            points.append(FundHistoryPoint(date=date, price=price, net_assets_million=net_assets))

    if not points:
        raise LookupError(f"{ticker}: Yahoo Finance Japan returned no fund history rows.")

    return FundHistory(
        name=parse_name(soup, ticker),
        source="Yahoo Finance Japan HTML",
        points=sorted(points, key=lambda point: point.date),
    )


def extract_jwt_token(html: str) -> str:
    marker = "window.__PRELOADED_STATE__ = "
    start = html.find(marker)
    if start < 0:
        raise LookupError("Yahoo Finance Japan page did not include a preloaded state token.")
    start += len(marker)
    end = html.find("</script>", start)
    if end < 0:
        raise LookupError("Yahoo Finance Japan preloaded state script was incomplete.")
    payload = json.loads(html[start:end].strip().rstrip(";"))
    token = payload.get("pageInfo", {}).get("jwtToken")
    if not token:
        raise LookupError("Yahoo Finance Japan page did not include a jwtToken.")
    return token


def parse_history_row(row: dict[str, object]) -> FundHistoryPoint | None:
    date = parse_japanese_date(str(row.get("date", "")))
    price = parse_number(str(row.get("price", "")))
    net_assets = parse_int(str(row.get("netAssetsBalance", "")))
    if not date or price is None:
        return None
    return FundHistoryPoint(date=date, price=price, net_assets_million=net_assets)


def parse_japanese_date(value: str) -> str | None:
    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    return datetime(year, month, day).date().isoformat()


def parse_number(value: str) -> float | None:
    normalized = value.replace(",", "").strip()
    if normalized in {"", "-", "--"}:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def parse_int(value: str) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def parse_name(soup: BeautifulSoup, fallback: str) -> str:
    title = soup.find("title")
    if not title:
        return fallback
    text = title.get_text("", strip=True)
    return text.split("【", 1)[0].strip() or fallback
