from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .database import get_db, init_db, seed_defaults
from .household import exclude_matching_bank_debit_withdrawals, insert_import_rows, parse_sample_files, parse_uploaded_csv_files
from .investment_support import PriceRow, build_indicators, build_investment_analysis, rsi
from .market import RANGE_TO_DAYS, normalize_ticker, refresh_symbols
from .models import (
    HouseholdAnalysisOut,
    HouseholdAssetPointOut,
    HouseholdCategorySummaryOut,
    HouseholdImportOut,
    HouseholdMonthlySummaryOut,
    HouseholdTransactionOut,
    HouseholdTransactionUpdate,
    ExternalDailyPricesOut,
    ExternalDailyPricePoint,
    ExternalMarketSnapshotOut,
    HistoryOut,
    InvestmentAnalysisOut,
    PricePoint,
    PurchaseCreate,
    PurchaseOut,
    QueueOut,
    RefreshJobOut,
    SymbolCreate,
    SymbolOrderUpdate,
    SymbolOut,
    SymbolUpdate,
    TaskCreate,
    TaskOut,
    TaskTagCreate,
    TaskTagOut,
    TaskTagUpdate,
    TaskUpdate,
)
from .refresh_queue import RefreshQueue, cancel_refresh_job, enqueue_refresh_jobs, list_refresh_jobs


refresh_queue = RefreshQueue()
AUTO_REFRESH_TIMEZONE = ZoneInfo("Asia/Tokyo")
AUTO_REFRESH_HOUR_JST = int(os.getenv("AUTO_REFRESH_HOUR_JST", "23"))
INVESTMENT_ANALYSIS_HOUR_JST = int(os.getenv("INVESTMENT_ANALYSIS_HOUR_JST", "1"))
INVESTMENT_ANALYSIS_HORIZON_DAYS = int(os.getenv("INVESTMENT_ANALYSIS_HORIZON_DAYS", "20"))
INVESTMENT_ANALYSIS_LOOKBACK_YEARS = int(os.getenv("INVESTMENT_ANALYSIS_LOOKBACK_YEARS", "5"))
EXTERNAL_API_KEY = os.getenv("EXTERNAL_API_KEY", "")
investment_analysis_task: asyncio.Task | None = None


async def daily_refresh_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_enqueue_if_stale)
            refresh_queue.notify()
        except Exception:
            pass
        await asyncio.sleep(60 * 60)


async def daily_investment_analysis_loop() -> None:
    while True:
        try:
            await _start_investment_analysis_if_stale()
        except Exception:
            pass
        await asyncio.sleep(60 * 60)


def _enqueue_if_stale() -> None:
    now_jst = datetime.now(AUTO_REFRESH_TIMEZONE)
    if now_jst.hour != AUTO_REFRESH_HOUR_JST:
        return
    refresh_date = now_jst.date().isoformat()
    with get_db() as db:
        row = db.execute("SELECT value FROM app_state WHERE key = 'last_auto_refresh_date_jst'").fetchone()
        if row and row["value"] == refresh_date:
            return
    enqueue_refresh_jobs()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO app_state (key, value, updated_at)
            VALUES ('last_auto_refresh_date_jst', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (refresh_date,),
        )


async def _start_investment_analysis_if_stale() -> None:
    now_jst = datetime.now(AUTO_REFRESH_TIMEZONE)
    if now_jst.hour != INVESTMENT_ANALYSIS_HOUR_JST:
        return
    analysis_date = now_jst.date().isoformat()
    with get_db() as db:
        row = db.execute("SELECT value FROM app_state WHERE key = 'last_investment_analysis_date_jst'").fetchone()
        if row and row["value"] == analysis_date:
            return
        db.execute(
            """
            INSERT INTO app_state (key, value, updated_at)
            VALUES ('last_investment_analysis_date_jst', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (analysis_date,),
        )
    await start_investment_analysis_recalculation(
        horizon_days=INVESTMENT_ANALYSIS_HORIZON_DAYS,
        lookback_years=INVESTMENT_ANALYSIS_LOOKBACK_YEARS,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_defaults()
    refresh_queue.start()
    refresh_task = asyncio.create_task(daily_refresh_loop())
    analysis_task = asyncio.create_task(daily_investment_analysis_loop())
    yield
    refresh_task.cancel()
    analysis_task.cancel()
    await refresh_queue.stop()


app = FastAPI(title="Pleiades API", version="0.1.0", lifespan=lifespan)

origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3050").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def symbol_from_row(row) -> SymbolOut:
    return SymbolOut(
        id=row["id"],
        ticker=row["ticker"],
        name=row["name"],
        asset_type=row["asset_type"],
        tag=row["tag"],
        display_order=row["display_order"],
        currency=row["currency"],
        exchange=row["exchange"],
        latest_close=row["latest_close"],
        latest_date=row["latest_date"],
        change_1d_percent=row["change_1d_percent"],
        per=row["per"],
        pbr=row["pbr"],
        roe=row["roe"],
        market_cap=row["market_cap"],
        dividend_yield=row["dividend_yield"],
        last_error=row["last_error"],
        last_refreshed_at=row["last_refreshed_at"],
    )


def symbol_query() -> str:
    return """
      WITH latest AS (
        SELECT
          symbol_id,
          date,
          close,
          LAG(close) OVER (PARTITION BY symbol_id ORDER BY date) AS previous_close,
          ROW_NUMBER() OVER (PARTITION BY symbol_id ORDER BY date DESC) AS rn
        FROM prices
      )
      SELECT
        s.id,
        s.ticker,
        s.name,
        s.asset_type,
        s.tag,
        s.display_order,
        s.currency,
        s.exchange,
        s.last_error,
        s.last_refreshed_at,
        l.close AS latest_close,
        l.date AS latest_date,
        CASE
          WHEN l.previous_close IS NULL OR l.previous_close = 0 THEN NULL
          ELSE ((l.close - l.previous_close) / l.previous_close) * 100
        END AS change_1d_percent,
        f.per,
        f.pbr,
        f.roe,
        f.market_cap,
        f.dividend_yield
      FROM symbols s
      LEFT JOIN latest l ON l.symbol_id = s.id AND l.rn = 1
      LEFT JOIN fundamentals f ON f.symbol_id = s.id
    """


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@app.get("/api/symbols", response_model=list[SymbolOut])
def list_symbols() -> list[SymbolOut]:
    with get_db() as db:
        rows = db.execute(f"{symbol_query()} ORDER BY s.display_order, s.id").fetchall()
    return [symbol_from_row(row) for row in rows]


@app.get("/api/external/market/symbols", response_model=ExternalMarketSnapshotOut)
def external_market_symbols(
    x_pleiades_api_key: str | None = Header(default=None),
) -> ExternalMarketSnapshotOut:
    require_external_api_key(x_pleiades_api_key)
    return ExternalMarketSnapshotOut(
        symbols=load_all_symbols(),
        generated_at=datetime.now(UTC).isoformat(),
    )


@app.get("/api/external/market/daily-prices/{ticker}", response_model=ExternalDailyPricesOut)
def external_daily_prices(
    ticker: str,
    from_date: str | None = Query(default=None, alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str | None = Query(default=None, alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    x_pleiades_api_key: str | None = Header(default=None),
) -> ExternalDailyPricesOut:
    require_external_api_key(x_pleiades_api_key)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="from must be earlier than or equal to to")

    normalized_ticker = normalize_ticker(ticker)
    price_filters = ["symbol_id = ?"]
    price_params: list[object] = []

    with get_db() as db:
        symbol_row = db.execute(f"{symbol_query()} WHERE s.ticker = ?", (normalized_ticker,)).fetchone()
        if symbol_row is None:
            raise HTTPException(status_code=404, detail="Symbol not found")

        price_params.append(symbol_row["id"])
        if from_date:
            price_filters.append("date >= ?")
            price_params.append(from_date)
        if to_date:
            price_filters.append("date <= ?")
            price_params.append(to_date)

        rows = db.execute(
            f"""
            SELECT date, open, high, low, close, adj_close, volume
            FROM prices
            WHERE {' AND '.join(price_filters)}
            ORDER BY date
            """,
            price_params,
        ).fetchall()
        indicator_rows = db.execute(
            """
            SELECT date, open, high, low, close, adj_close, volume
            FROM prices
            WHERE symbol_id = ?
            ORDER BY date
            """,
            (symbol_row["id"],),
        ).fetchall()

    return ExternalDailyPricesOut(
        symbol=symbol_from_row(symbol_row),
        points=external_price_points_from_rows(rows, indicator_rows),
        generated_at=datetime.now(UTC).isoformat(),
        from_date=from_date,
        to_date=to_date,
    )


def load_all_symbols() -> list[SymbolOut]:
    with get_db() as db:
        rows = db.execute(f"{symbol_query()} ORDER BY s.display_order, s.id").fetchall()
    return [symbol_from_row(row) for row in rows]


def app_state_values(keys: list[str]) -> dict[str, str]:
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    with get_db() as db:
        rows = db.execute(f"SELECT key, value FROM app_state WHERE key IN ({placeholders})", keys).fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_app_state(values: dict[str, str]) -> None:
    with get_db() as db:
        for key, value in values.items():
            db.execute(
                """
                INSERT INTO app_state (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )


def require_external_api_key(x_pleiades_api_key: str | None) -> None:
    if EXTERNAL_API_KEY and x_pleiades_api_key != EXTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid external API key")


def price_points_from_rows(rows) -> list[PricePoint]:
    first_close = next((row["close"] for row in rows if row["close"]), None)
    return [
        PricePoint(
            date=row["date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            adj_close=row["adj_close"],
            volume=row["volume"],
            return_percent=((row["close"] - first_close) / first_close * 100)
            if row["close"] is not None and first_close
            else None,
        )
        for row in rows
    ]


def external_price_points_from_rows(rows, indicator_rows) -> list[ExternalDailyPricePoint]:
    first_close = next((row["close"] for row in rows if row["close"]), None)
    indicators_by_date = technical_indicators_by_date(indicator_rows)
    return [
        ExternalDailyPricePoint(
            date=row["date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            adj_close=row["adj_close"],
            volume=row["volume"],
            return_percent=((row["close"] - first_close) / first_close * 100)
            if row["close"] is not None and first_close
            else None,
            **indicators_by_date.get(row["date"], {}),
        )
        for row in rows
    ]


def technical_indicators_by_date(rows) -> dict[str, dict[str, float | None]]:
    price_rows = [
        PriceRow(
            date=row["date"],
            open=row["open"],
            close=row["close"],
            high=row["high"],
            low=row["low"],
            volume=row["volume"],
        )
        for row in rows
        if row["close"] is not None and row["close"] > 0
    ]
    if not price_rows:
        return {}
    indicators = build_indicators(price_rows)
    return {
        row.date: {
            "ma20": indicators.ma20[index],
            "ma60": indicators.ma60[index],
            "ma200": indicators.ma200[index],
            "macd_histogram": indicators.macd_hist[index],
            "bb_upper_2sigma": indicators.bb_upper_2[index],
            "bb_lower_2sigma": indicators.bb_lower_2[index],
            "rsi_14": rsi(price_rows, index, 14),
        }
        for index, row in enumerate(price_rows)
    }


def get_cached_investment_analysis() -> InvestmentAnalysisOut:
    values = app_state_values(
        [
            "investment_analysis_payload",
            "investment_analysis_status",
            "investment_analysis_error",
            "investment_analysis_last_started_at",
            "investment_analysis_last_finished_at",
            "investment_analysis_horizon_days",
            "investment_analysis_lookback_years",
        ]
    )
    horizon_days = int(values.get("investment_analysis_horizon_days", INVESTMENT_ANALYSIS_HORIZON_DAYS))
    lookback_years = int(values.get("investment_analysis_lookback_years", INVESTMENT_ANALYSIS_LOOKBACK_YEARS))
    payload = values.get("investment_analysis_payload")
    if payload:
        try:
            analysis = InvestmentAnalysisOut(**json.loads(payload))
        except Exception:
            analysis = InvestmentAnalysisOut(
                rules=[],
                signals=[],
                generated_at=None,
                horizon_days=horizon_days,
                lookback_years=lookback_years,
            )
    else:
        analysis = InvestmentAnalysisOut(
            rules=[],
            signals=[],
            generated_at=None,
            horizon_days=horizon_days,
            lookback_years=lookback_years,
        )
    analysis.status = values.get("investment_analysis_status", analysis.status)
    analysis.error = values.get("investment_analysis_error")
    analysis.last_started_at = values.get("investment_analysis_last_started_at")
    analysis.last_finished_at = values.get("investment_analysis_last_finished_at")
    return analysis


async def start_investment_analysis_recalculation(horizon_days: int, lookback_years: int) -> InvestmentAnalysisOut:
    global investment_analysis_task
    if investment_analysis_task and not investment_analysis_task.done():
        return get_cached_investment_analysis()
    started_at = datetime.now(UTC).isoformat()
    set_app_state(
        {
            "investment_analysis_status": "running",
            "investment_analysis_error": "",
            "investment_analysis_last_started_at": started_at,
            "investment_analysis_horizon_days": str(horizon_days),
            "investment_analysis_lookback_years": str(lookback_years),
        }
    )
    investment_analysis_task = asyncio.create_task(run_investment_analysis_recalculation(horizon_days, lookback_years))
    return get_cached_investment_analysis()


async def run_investment_analysis_recalculation(horizon_days: int, lookback_years: int) -> None:
    started_at = datetime.now(UTC).isoformat()
    set_app_state(
        {
            "investment_analysis_status": "running",
            "investment_analysis_error": "",
            "investment_analysis_last_started_at": started_at,
            "investment_analysis_horizon_days": str(horizon_days),
            "investment_analysis_lookback_years": str(lookback_years),
        }
    )
    try:
        analysis = await asyncio.to_thread(
            lambda: build_investment_analysis(
                load_all_symbols(),
                horizon_days,
                lookback_years,
            )
        )
        finished_at = datetime.now(UTC).isoformat()
        analysis.status = "succeeded"
        analysis.last_started_at = started_at
        analysis.last_finished_at = finished_at
        set_app_state(
            {
                "investment_analysis_status": "succeeded",
                "investment_analysis_error": "",
                "investment_analysis_last_started_at": started_at,
                "investment_analysis_last_finished_at": finished_at,
                "investment_analysis_payload": analysis.model_dump_json(),
            }
        )
    except Exception as exc:
        set_app_state(
            {
                "investment_analysis_status": "failed",
                "investment_analysis_error": str(exc),
                "investment_analysis_last_finished_at": datetime.now(UTC).isoformat(),
            }
        )


@app.get("/api/investment-support/analysis", response_model=InvestmentAnalysisOut)
def investment_support_analysis() -> InvestmentAnalysisOut:
    return get_cached_investment_analysis()


@app.post("/api/investment-support/analysis/recalculate", response_model=InvestmentAnalysisOut)
async def recalculate_investment_support_analysis(
    horizon_days: int = Query(default=INVESTMENT_ANALYSIS_HORIZON_DAYS, ge=1, le=260),
    lookback_years: int = Query(default=INVESTMENT_ANALYSIS_LOOKBACK_YEARS, ge=1, le=20),
) -> InvestmentAnalysisOut:
    return await start_investment_analysis_recalculation(horizon_days=horizon_days, lookback_years=lookback_years)


@app.post("/api/symbols", response_model=SymbolOut)
def create_symbol(payload: SymbolCreate) -> SymbolOut:
    ticker = normalize_ticker(payload.ticker)
    name = payload.name.strip() if payload.name else ticker
    tag = (payload.tag or "ウォッチリスト").strip() or "ウォッチリスト"
    with get_db() as db:
        display_order = db.execute(
            "SELECT COALESCE(MAX(display_order), 0) + 10 AS next_order FROM symbols",
        ).fetchone()["next_order"]
        try:
            cursor = db.execute(
                "INSERT INTO symbols (ticker, name, asset_type, tag, display_order) VALUES (?, ?, ?, ?, ?)",
                (ticker, name, payload.asset_type, tag, display_order),
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"{ticker} is already registered") from exc
        row = db.execute(f"{symbol_query()} WHERE s.id = ?", (cursor.lastrowid,)).fetchone()
    enqueue_refresh_jobs([row["id"]])
    refresh_queue.notify()
    return symbol_from_row(row)


@app.patch("/api/symbols/{symbol_id}", response_model=SymbolOut)
def update_symbol(symbol_id: int, payload: SymbolUpdate) -> SymbolOut:
    with get_db() as db:
        current = db.execute("SELECT id, tag FROM symbols WHERE id = ?", (symbol_id,)).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Symbol not found")
        if payload.tag is not None:
            tag = payload.tag.strip() or "ウォッチリスト"
            display_order = db.execute(
                "SELECT COALESCE(MAX(display_order), 0) + 10 AS next_order FROM symbols WHERE id != ?",
                (symbol_id,),
            ).fetchone()["next_order"]
            db.execute(
                """
                UPDATE symbols
                SET tag = ?, display_order = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (tag, display_order, symbol_id),
            )
        row = db.execute(f"{symbol_query()} WHERE s.id = ?", (symbol_id,)).fetchone()
    return symbol_from_row(row)


@app.put("/api/symbols/order", response_model=list[SymbolOut])
def update_symbol_order(payload: SymbolOrderUpdate) -> list[SymbolOut]:
    with get_db() as db:
        placeholders = ",".join("?" for _ in payload.symbol_ids)
        rows = db.execute(f"SELECT id FROM symbols WHERE id IN ({placeholders})", payload.symbol_ids).fetchall()
        found_ids = {row["id"] for row in rows}
        missing_ids = [symbol_id for symbol_id in payload.symbol_ids if symbol_id not in found_ids]
        if missing_ids:
            raise HTTPException(status_code=404, detail=f"Symbols not found: {missing_ids}")
        for index, symbol_id in enumerate(payload.symbol_ids):
            db.execute(
                "UPDATE symbols SET display_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                ((index + 1) * 10, symbol_id),
            )
        rows = db.execute(f"{symbol_query()} ORDER BY s.display_order, s.id").fetchall()
    return [symbol_from_row(row) for row in rows]


@app.delete("/api/symbols/{symbol_id}")
def delete_symbol(symbol_id: int) -> dict[str, str]:
    with get_db() as db:
        result = db.execute("DELETE FROM symbols WHERE id = ?", (symbol_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Symbol not found")
    return {"status": "deleted"}


@app.post("/api/refresh", response_model=QueueOut)
def refresh_all() -> QueueOut:
    job_ids = enqueue_refresh_jobs()
    refresh_queue.notify()
    return QueueOut(queued=len(job_ids), job_ids=job_ids)


@app.post("/api/symbols/{symbol_id}/refresh", response_model=QueueOut)
def refresh_symbol(symbol_id: int) -> QueueOut:
    with get_db() as db:
        row = db.execute("SELECT id FROM symbols WHERE id = ?", (symbol_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Symbol not found")
    job_ids = enqueue_refresh_jobs([symbol_id])
    refresh_queue.notify()
    return QueueOut(queued=len(job_ids), job_ids=job_ids)


@app.get("/api/refresh/jobs", response_model=list[RefreshJobOut])
def refresh_jobs(limit: int = Query(default=50, ge=1, le=200)) -> list[RefreshJobOut]:
    return [RefreshJobOut(**row) for row in list_refresh_jobs(limit)]


@app.post("/api/refresh/jobs/{job_id}/cancel", response_model=RefreshJobOut)
def cancel_job(job_id: int) -> RefreshJobOut:
    try:
        row = cancel_refresh_job(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    refresh_queue.notify()
    return RefreshJobOut(**row)


def purchase_from_row(row) -> PurchaseOut:
    return PurchaseOut(
        id=row["id"],
        symbol_id=row["symbol_id"],
        purchased_at=row["purchased_at"],
        amount=row["amount"],
        quantity=row["quantity"],
        unit_price=row["amount"] / row["quantity"],
        note=row["note"],
        created_at=row["created_at"],
    )


def task_tag_from_row(row) -> TaskTagOut:
    return TaskTagOut(
        id=row["id"],
        name=row["name"],
        color=row["color"],
        hidden=bool(row["hidden"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def task_from_row(row, tags: list[TaskTagOut]) -> TaskOut:
    return TaskOut(
        id=row["id"],
        title=row["title"],
        status=row["status"],
        due_date=row["due_date"],
        duration_days=row["duration_days"],
        tags=tags,
        details=row["details"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def household_transaction_from_row(row) -> HouseholdTransactionOut:
    return HouseholdTransactionOut(
        id=row["id"],
        transacted_at=row["transacted_at"],
        amount=row["amount"],
        direction=row["direction"],
        category=row["category"],
        merchant=row["merchant"],
        description=row["description"],
        source_type=row["source_type"],
        balance_after=row["balance_after"],
        memo=row["memo"],
        excluded=bool(row["excluded"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def fetch_task_tags(db, task_ids: list[int]) -> dict[int, list[TaskTagOut]]:
    if not task_ids:
        return {}
    placeholders = ",".join("?" for _ in task_ids)
    rows = db.execute(
        f"""
        SELECT ttl.task_id, tt.id, tt.name, tt.color, tt.hidden, tt.created_at, tt.updated_at
        FROM task_tag_links ttl
        JOIN task_tags tt ON tt.id = ttl.tag_id
        WHERE ttl.task_id IN ({placeholders})
        ORDER BY tt.name, tt.id
        """,
        task_ids,
    ).fetchall()
    tags_by_task = {task_id: [] for task_id in task_ids}
    for row in rows:
        tags_by_task[row["task_id"]].append(task_tag_from_row(row))
    return tags_by_task


def replace_task_tags(db, task_id: int, tag_ids: list[int]) -> None:
    unique_ids = list(dict.fromkeys(tag_ids))
    if unique_ids:
        placeholders = ",".join("?" for _ in unique_ids)
        rows = db.execute(f"SELECT id FROM task_tags WHERE id IN ({placeholders})", unique_ids).fetchall()
        found_ids = {row["id"] for row in rows}
        missing_ids = [tag_id for tag_id in unique_ids if tag_id not in found_ids]
        if missing_ids:
            raise HTTPException(status_code=404, detail=f"Task tags not found: {missing_ids}")
    db.execute("DELETE FROM task_tag_links WHERE task_id = ?", (task_id,))
    for tag_id in unique_ids:
        db.execute("INSERT INTO task_tag_links (task_id, tag_id) VALUES (?, ?)", (task_id, tag_id))


def get_task_or_404(db, task_id: int) -> TaskOut:
    row = db.execute(
        """
        SELECT id, title, status, due_date, duration_days, details, completed_at, created_at, updated_at
        FROM tasks
        WHERE id = ?
        """,
        (task_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    tags = fetch_task_tags(db, [task_id]).get(task_id, [])
    return task_from_row(row, tags)


@app.get("/api/task-tags", response_model=list[TaskTagOut])
def list_task_tags() -> list[TaskTagOut]:
    with get_db() as db:
        rows = db.execute(
            "SELECT id, name, color, hidden, created_at, updated_at FROM task_tags ORDER BY name, id"
        ).fetchall()
    return [task_tag_from_row(row) for row in rows]


@app.post("/api/task-tags", response_model=TaskTagOut)
def create_task_tag(payload: TaskTagCreate) -> TaskTagOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tag name is required")
    with get_db() as db:
        try:
            cursor = db.execute(
                "INSERT INTO task_tags (name, color) VALUES (?, ?)",
                (name, payload.color),
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"{name} is already registered") from exc
        row = db.execute(
            "SELECT id, name, color, hidden, created_at, updated_at FROM task_tags WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return task_tag_from_row(row)


@app.patch("/api/task-tags/{tag_id}", response_model=TaskTagOut)
def update_task_tag(tag_id: int, payload: TaskTagUpdate) -> TaskTagOut:
    fields = payload.model_fields_set
    if not fields:
        with get_db() as db:
            row = db.execute(
                "SELECT id, name, color, hidden, created_at, updated_at FROM task_tags WHERE id = ?",
                (tag_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Task tag not found")
            return task_tag_from_row(row)
    updates = []
    values: list[object] = []
    if "name" in fields:
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Tag name is required")
        updates.append("name = ?")
        values.append(name)
    if "color" in fields:
        if payload.color is None:
            raise HTTPException(status_code=422, detail="Tag color is required")
        updates.append("color = ?")
        values.append(payload.color)
    if "hidden" in fields:
        updates.append("hidden = ?")
        values.append(1 if payload.hidden else 0)
    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(tag_id)
    with get_db() as db:
        try:
            result = db.execute(f"UPDATE task_tags SET {', '.join(updates)} WHERE id = ?", values)
        except Exception as exc:
            raise HTTPException(status_code=409, detail="Task tag update conflicted") from exc
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task tag not found")
        row = db.execute(
            "SELECT id, name, color, hidden, created_at, updated_at FROM task_tags WHERE id = ?",
            (tag_id,),
        ).fetchone()
    return task_tag_from_row(row)


@app.delete("/api/task-tags/{tag_id}")
def delete_task_tag(tag_id: int) -> dict[str, str]:
    with get_db() as db:
        result = db.execute("DELETE FROM task_tags WHERE id = ?", (tag_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task tag not found")
    return {"status": "deleted"}


@app.post("/api/household/import-samples", response_model=HouseholdImportOut)
def import_household_samples() -> HouseholdImportOut:
    try:
        rows = parse_sample_files()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV import failed: {exc}") from exc
    with get_db() as db:
        result = insert_import_rows(db, rows)
        result["excluded"] = exclude_matching_bank_debit_withdrawals(db, rows)
    return HouseholdImportOut(**result)


@app.post("/api/household/import-csv", response_model=HouseholdImportOut)
async def import_household_csv(files: list[UploadFile] = File(...)) -> HouseholdImportOut:
    if not files:
        raise HTTPException(status_code=422, detail="CSV file is required")
    try:
        contents = [await file.read() for file in files]
        rows = parse_uploaded_csv_files(contents)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV import failed: {exc}") from exc
    with get_db() as db:
        result = insert_import_rows(db, rows)
        result["excluded"] = exclude_matching_bank_debit_withdrawals(db, rows)
    return HouseholdImportOut(**result)


@app.get("/api/household/analysis", response_model=HouseholdAnalysisOut)
def household_analysis(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$|^$")) -> HouseholdAnalysisOut:
    filters = ["excluded = 0"]
    values: list[object] = []
    if month:
        filters.append("substr(transacted_at, 1, 7) = ?")
        values.append(month)
    where_clause = "WHERE " + " AND ".join(filters)
    with get_db() as db:
        transaction_rows = db.execute(
            f"""
            SELECT id, transacted_at, amount, direction, category, merchant, description,
                   source_type, balance_after, memo, excluded, created_at, updated_at
            FROM household_transactions
            {where_clause}
            ORDER BY transacted_at DESC, id DESC
            LIMIT 500
            """,
            values,
        ).fetchall()
        monthly_rows = db.execute(
            """
            SELECT
              substr(transacted_at, 1, 7) AS month,
              SUM(CASE WHEN direction = 'income' THEN amount ELSE 0 END) AS income,
              SUM(CASE WHEN direction = 'expense' THEN amount ELSE 0 END) AS expense
            FROM household_transactions
            WHERE excluded = 0
            GROUP BY substr(transacted_at, 1, 7)
            ORDER BY month DESC
            """
        ).fetchall()
        category_rows = db.execute(
            f"""
            SELECT category, SUM(amount) AS expense, COUNT(*) AS transaction_count
            FROM household_transactions
            {where_clause} AND direction = 'expense'
            GROUP BY category
            ORDER BY expense DESC, category
            """,
            values,
        ).fetchall()
        total_row = db.execute(
            f"""
            SELECT
              SUM(CASE WHEN direction = 'income' THEN amount ELSE 0 END) AS income,
              SUM(CASE WHEN direction = 'expense' THEN amount ELSE 0 END) AS expense
            FROM household_transactions
            {where_clause}
            """,
            values,
        ).fetchone()
        largest_row = db.execute(
            f"""
            SELECT id, transacted_at, amount, direction, category, merchant, description,
                   source_type, balance_after, memo, excluded, created_at, updated_at
            FROM household_transactions
            {where_clause} AND direction = 'expense'
            ORDER BY amount DESC, transacted_at DESC
            LIMIT 1
            """,
            values,
        ).fetchone()
        asset_rows = db.execute(
            """
            SELECT transacted_at AS date, balance_after AS balance
            FROM (
              SELECT
                transacted_at,
                balance_after,
                ROW_NUMBER() OVER (PARTITION BY transacted_at ORDER BY id DESC) AS rn
              FROM household_transactions
              WHERE source_type = 'bank' AND balance_after IS NOT NULL
            )
            WHERE rn = 1
            ORDER BY date
            """
        ).fetchall()

    transactions = [household_transaction_from_row(row) for row in transaction_rows]
    monthly = []
    for row in monthly_rows:
        income = row["income"] or 0
        expense = row["expense"] or 0
        monthly.append(
            HouseholdMonthlySummaryOut(
                month=row["month"],
                income=income,
                expense=expense,
                net=income - expense,
                savings_rate_percent=((income - expense) / income * 100) if income else None,
            )
        )
    total_income = total_row["income"] or 0
    total_expense = total_row["expense"] or 0
    categories = [
        HouseholdCategorySummaryOut(
            category=row["category"],
            expense=row["expense"] or 0,
            transaction_count=row["transaction_count"],
            share_percent=((row["expense"] or 0) / total_expense * 100) if total_expense else None,
        )
        for row in category_rows
    ]
    monthly_expenses = [row.expense for row in monthly if row.expense > 0]
    return HouseholdAnalysisOut(
        transactions=transactions,
        monthly=monthly,
        categories=categories,
        asset_points=[HouseholdAssetPointOut(date=row["date"], balance=row["balance"]) for row in asset_rows],
        total_income=total_income,
        total_expense=total_expense,
        net=total_income - total_expense,
        average_monthly_expense=sum(monthly_expenses) / len(monthly_expenses) if monthly_expenses else 0,
        largest_expense=household_transaction_from_row(largest_row) if largest_row else None,
    )


@app.patch("/api/household/transactions/{transaction_id}", response_model=HouseholdTransactionOut)
def update_household_transaction(transaction_id: int, payload: HouseholdTransactionUpdate) -> HouseholdTransactionOut:
    fields = payload.model_fields_set
    if not fields:
        with get_db() as db:
            row = db.execute(
                """
                SELECT id, transacted_at, amount, direction, category, merchant, description,
                       source_type, balance_after, memo, excluded, created_at, updated_at
                FROM household_transactions
                WHERE id = ?
                """,
                (transaction_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Household transaction not found")
            return household_transaction_from_row(row)
    updates = []
    values: list[object] = []
    if "category" in fields:
        category = (payload.category or "").strip()
        if not category:
            raise HTTPException(status_code=422, detail="Category is required")
        updates.append("category = ?")
        values.append(category)
    if "memo" in fields:
        updates.append("memo = ?")
        values.append(payload.memo or "")
    if "excluded" in fields:
        updates.append("excluded = ?")
        values.append(1 if payload.excluded else 0)
    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(transaction_id)
    with get_db() as db:
        result = db.execute(f"UPDATE household_transactions SET {', '.join(updates)} WHERE id = ?", values)
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Household transaction not found")
        row = db.execute(
            """
            SELECT id, transacted_at, amount, direction, category, merchant, description,
                   source_type, balance_after, memo, excluded, created_at, updated_at
            FROM household_transactions
            WHERE id = ?
            """,
            (transaction_id,),
        ).fetchone()
    return household_transaction_from_row(row)


@app.get("/api/tasks", response_model=list[TaskOut])
def list_tasks() -> list[TaskOut]:
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, title, status, due_date, duration_days, details, completed_at, created_at, updated_at
            FROM tasks
            ORDER BY
              CASE WHEN status = 'done' THEN 1 ELSE 0 END,
              COALESCE(due_date, '9999-12-31'),
              id DESC
            """
        ).fetchall()
        task_ids = [row["id"] for row in rows]
        tags_by_task = fetch_task_tags(db, task_ids)
    return [task_from_row(row, tags_by_task.get(row["id"], [])) for row in rows]


@app.post("/api/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate) -> TaskOut:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Task title is required")
    completed_at = datetime.now(UTC).isoformat() if payload.status == "done" else None
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO tasks (title, status, due_date, duration_days, details, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title, payload.status, payload.due_date or None, payload.duration_days, payload.details, completed_at),
        )
        replace_task_tags(db, cursor.lastrowid, payload.tag_ids)
        task = get_task_or_404(db, cursor.lastrowid)
    return task


@app.patch("/api/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate) -> TaskOut:
    fields = payload.model_fields_set
    with get_db() as db:
        current = db.execute("SELECT id, status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Task not found")
        updates = []
        values: list[object] = []
        if "title" in fields:
            title = (payload.title or "").strip()
            if not title:
                raise HTTPException(status_code=422, detail="Task title is required")
            updates.append("title = ?")
            values.append(title)
        if "status" in fields:
            if payload.status is None:
                raise HTTPException(status_code=422, detail="Task status is required")
            updates.append("status = ?")
            values.append(payload.status)
            if payload.status == "done" and current["status"] != "done":
                updates.append("completed_at = ?")
                values.append(datetime.now(UTC).isoformat())
            elif payload.status != "done":
                updates.append("completed_at = NULL")
        if "due_date" in fields:
            updates.append("due_date = ?")
            values.append(payload.due_date or None)
        if "duration_days" in fields:
            updates.append("duration_days = ?")
            values.append(payload.duration_days)
        if "details" in fields:
            updates.append("details = ?")
            values.append(payload.details or "")
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            values.append(task_id)
            db.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
        if payload.tag_ids is not None:
            replace_task_tags(db, task_id, payload.tag_ids)
            db.execute("UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
        task = get_task_or_404(db, task_id)
    return task


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int) -> dict[str, str]:
    with get_db() as db:
        result = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted"}


@app.get("/api/symbols/{symbol_id}/purchases", response_model=list[PurchaseOut])
def list_purchases(symbol_id: int) -> list[PurchaseOut]:
    with get_db() as db:
        symbol = db.execute("SELECT id FROM symbols WHERE id = ?", (symbol_id,)).fetchone()
        if symbol is None:
            raise HTTPException(status_code=404, detail="Symbol not found")
        rows = db.execute(
            """
            SELECT id, symbol_id, purchased_at, amount, quantity, note, created_at
            FROM purchases
            WHERE symbol_id = ?
            ORDER BY purchased_at DESC, id DESC
            """,
            (symbol_id,),
        ).fetchall()
    return [purchase_from_row(row) for row in rows]


@app.post("/api/symbols/{symbol_id}/purchases", response_model=PurchaseOut)
def create_purchase(symbol_id: int, payload: PurchaseCreate) -> PurchaseOut:
    with get_db() as db:
        symbol = db.execute("SELECT id, asset_type FROM symbols WHERE id = ?", (symbol_id,)).fetchone()
        if symbol is None:
            raise HTTPException(status_code=404, detail="Symbol not found")
        quantity = payload.quantity
        if quantity is None:
            if symbol["asset_type"] == "stock":
                raise HTTPException(status_code=422, detail="Quantity is required for stock purchases")
            purchase_close = purchase_price_near_date(db, symbol_id, payload.purchased_at)
            if purchase_close is None or purchase_close <= 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"No price history is available near {payload.purchased_at}",
                )
            quantity = payload.amount / purchase_close
        cursor = db.execute(
            """
            INSERT INTO purchases (symbol_id, purchased_at, amount, quantity, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (symbol_id, payload.purchased_at, payload.amount, quantity, payload.note),
        )
        row = db.execute(
            """
            SELECT id, symbol_id, purchased_at, amount, quantity, note, created_at
            FROM purchases
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return purchase_from_row(row)


def purchase_price_near_date(db, symbol_id: int, purchased_at: str) -> float | None:
    row = db.execute(
        """
        SELECT close
        FROM prices
        WHERE symbol_id = ? AND date >= ? AND close IS NOT NULL
        ORDER BY date
        LIMIT 1
        """,
        (symbol_id, purchased_at),
    ).fetchone()
    if row is not None:
        return row["close"]
    row = db.execute(
        """
        SELECT close
        FROM prices
        WHERE symbol_id = ? AND close IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
        """,
        (symbol_id,),
    ).fetchone()
    return row["close"] if row is not None else None


@app.delete("/api/purchases/{purchase_id}")
def delete_purchase(purchase_id: int) -> dict[str, str]:
    with get_db() as db:
        result = db.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Purchase not found")
    return {"status": "deleted"}


@app.get("/api/symbols/{symbol_id}/history", response_model=HistoryOut)
def history(symbol_id: int, range: str = Query(default="1y", pattern="^(1w|1m|3m|1y|2y|3y|5y)$")) -> HistoryOut:
    since = (datetime.now(UTC).date() - timedelta(days=RANGE_TO_DAYS[range])).isoformat()
    with get_db() as db:
        symbol_row = db.execute(f"{symbol_query()} WHERE s.id = ?", (symbol_id,)).fetchone()
        if symbol_row is None:
            raise HTTPException(status_code=404, detail="Symbol not found")
        rows = db.execute(
            """
            SELECT date, open, high, low, close, adj_close, volume
            FROM prices
            WHERE symbol_id = ? AND date >= ?
            ORDER BY date
            """,
            (symbol_id, since),
        ).fetchall()

    return HistoryOut(symbol=symbol_from_row(symbol_row), points=price_points_from_rows(rows))
