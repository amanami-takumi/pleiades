from __future__ import annotations

from pydantic import BaseModel, Field


class SymbolCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=120)
    asset_type: str = Field(default="stock", max_length=32)
    tag: str | None = Field(default=None, max_length=80)


class SymbolUpdate(BaseModel):
    tag: str | None = Field(default=None, max_length=80)


class SymbolOrderUpdate(BaseModel):
    symbol_ids: list[int] = Field(min_length=1)


class SymbolOut(BaseModel):
    id: int
    ticker: str
    name: str
    asset_type: str
    tag: str
    display_order: int
    currency: str | None = None
    exchange: str | None = None
    latest_close: float | None = None
    latest_date: str | None = None
    change_1d_percent: float | None = None
    per: float | None = None
    pbr: float | None = None
    roe: float | None = None
    market_cap: float | None = None
    dividend_yield: float | None = None
    last_error: str | None = None
    last_refreshed_at: str | None = None


class PricePoint(BaseModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adj_close: float | None = None
    volume: int | None = None
    return_percent: float | None = None


class HistoryOut(BaseModel):
    symbol: SymbolOut
    points: list[PricePoint]


class RefreshOut(BaseModel):
    refreshed: list[str]
    errors: dict[str, str]


class QueueOut(BaseModel):
    queued: int
    job_ids: list[int]


class RefreshJobOut(BaseModel):
    id: int
    symbol_id: int | None = None
    ticker: str
    status: str
    error: str | None = None
    cancel_requested: bool = False
    queued_at: str
    started_at: str | None = None
    finished_at: str | None = None


class PurchaseCreate(BaseModel):
    purchased_at: str = Field(min_length=1, max_length=20)
    amount: float = Field(gt=0)
    quantity: float = Field(gt=0)
    note: str | None = Field(default=None, max_length=200)


class PurchaseOut(BaseModel):
    id: int
    symbol_id: int
    purchased_at: str
    amount: float
    quantity: float
    unit_price: float
    note: str | None = None
    created_at: str
