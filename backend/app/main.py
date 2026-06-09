from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .database import get_db, init_db, seed_defaults
from .market import RANGE_TO_DAYS, normalize_ticker, refresh_symbols
from .models import (
    HistoryOut,
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


async def daily_refresh_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_enqueue_if_stale)
            refresh_queue.notify()
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_defaults()
    refresh_queue.start()
    task = asyncio.create_task(daily_refresh_loop())
    yield
    task.cancel()
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

    first_close = next((row["close"] for row in rows if row["close"]), None)
    points = [
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
    return HistoryOut(symbol=symbol_from_row(symbol_row), points=points)
