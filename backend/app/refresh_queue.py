from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from .database import get_db
from .market import refresh_symbol_row


REFRESH_JOB_INTERVAL_SECONDS = float(os.getenv("REFRESH_JOB_INTERVAL_SECONDS", "5"))


class RefreshQueue:
    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def notify(self) -> None:
        self._event.set()

    async def _run(self) -> None:
        while True:
            processed = await asyncio.to_thread(process_next_job)
            if not processed:
                self._event.clear()
                await self._event.wait()
            elif REFRESH_JOB_INTERVAL_SECONDS > 0:
                await asyncio.sleep(REFRESH_JOB_INTERVAL_SECONDS)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def enqueue_refresh_jobs(symbol_ids: list[int] | None = None) -> list[int]:
    with get_db() as db:
        if symbol_ids:
            placeholders = ",".join("?" for _ in symbol_ids)
            rows = db.execute(
                f"SELECT id, ticker FROM symbols WHERE id IN ({placeholders}) ORDER BY id",
                tuple(symbol_ids),
            ).fetchall()
        else:
            rows = db.execute("SELECT id, ticker FROM symbols ORDER BY id").fetchall()

        job_ids: list[int] = []
        for row in rows:
            cursor = db.execute(
                """
                INSERT INTO refresh_jobs (symbol_id, ticker, status)
                VALUES (?, ?, 'queued')
                """,
                (row["id"], row["ticker"]),
            )
            job_ids.append(cursor.lastrowid)
    return job_ids


def list_refresh_jobs(limit: int = 50) -> list[dict[str, object]]:
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, symbol_id, ticker, status, error, cancel_requested, queued_at, started_at, finished_at
            FROM refresh_jobs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def cancel_refresh_job(job_id: int) -> dict[str, object]:
    with get_db() as db:
        job = db.execute(
            """
            SELECT id, symbol_id, ticker, status, error, cancel_requested, queued_at, started_at, finished_at
            FROM refresh_jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()
        if job is None:
            raise LookupError("Refresh job not found")

        if job["status"] == "queued":
            db.execute(
                """
                UPDATE refresh_jobs
                SET status = 'cancelled',
                    cancel_requested = 1,
                    finished_at = ?,
                    error = 'Cancelled before start'
                WHERE id = ?
                """,
                (utc_now(), job_id),
            )
        elif job["status"] == "running":
            db.execute(
                """
                UPDATE refresh_jobs
                SET cancel_requested = 1,
                    error = 'Cancellation requested'
                WHERE id = ?
                """,
                (job_id,),
            )

        updated = db.execute(
            """
            SELECT id, symbol_id, ticker, status, error, cancel_requested, queued_at, started_at, finished_at
            FROM refresh_jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()
    return dict(updated)


def process_next_job() -> bool:
    with get_db() as db:
        job = db.execute(
            """
            SELECT id, symbol_id, ticker, cancel_requested
            FROM refresh_jobs
            WHERE status = 'queued'
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
        if job is None:
            return False

        if job["cancel_requested"]:
            db.execute(
                """
                UPDATE refresh_jobs
                SET status = 'cancelled', finished_at = ?, error = 'Cancelled before start'
                WHERE id = ?
                """,
                (utc_now(), job["id"]),
            )
            return True

        db.execute(
            """
            UPDATE refresh_jobs
            SET status = 'running', started_at = ?, error = NULL
            WHERE id = ?
            """,
            (utc_now(), job["id"]),
        )

    try:
        if job["symbol_id"] is None:
            raise LookupError(f"{job['ticker']}: symbol was deleted")
        with get_db() as db:
            refresh_symbol_row(db, job["symbol_id"])
        with get_db() as db:
            updated = db.execute(
                "SELECT cancel_requested FROM refresh_jobs WHERE id = ?",
                (job["id"],),
            ).fetchone()
            if updated and updated["cancel_requested"]:
                db.execute(
                    """
                    UPDATE refresh_jobs
                    SET status = 'cancelled', finished_at = ?, error = 'Cancelled after current fetch completed'
                    WHERE id = ?
                    """,
                    (utc_now(), job["id"]),
                )
            else:
                db.execute(
                    """
                    UPDATE refresh_jobs
                    SET status = 'succeeded', finished_at = ?, error = NULL
                    WHERE id = ?
                    """,
                    (utc_now(), job["id"]),
                )
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        with get_db() as db:
            db.execute(
                """
                UPDATE refresh_jobs
                SET status = 'failed', finished_at = ?, error = ?
                WHERE id = ?
                """,
                (utc_now(), message, job["id"]),
            )
            if job["symbol_id"] is not None:
                db.execute(
                    """
                    UPDATE symbols
                    SET last_error = ?, last_refreshed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (message, job["symbol_id"]),
                )
    return True
