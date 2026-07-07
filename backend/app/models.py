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


class ExternalDailyPricePoint(PricePoint):
    ma20: float | None = None
    ma60: float | None = None
    ma200: float | None = None
    macd_histogram: float | None = None
    bb_upper_2sigma: float | None = None
    bb_lower_2sigma: float | None = None
    rsi_14: float | None = None


class HistoryOut(BaseModel):
    symbol: SymbolOut
    points: list[PricePoint]


class ExternalDailyPricesOut(BaseModel):
    symbol: SymbolOut
    points: list[ExternalDailyPricePoint]
    generated_at: str
    from_date: str | None = None
    to_date: str | None = None


class ExternalMarketSnapshotOut(BaseModel):
    symbols: list[SymbolOut]
    generated_at: str


class AnalysisBacktestOut(BaseModel):
    signals: int
    correct: int
    accuracy_percent: float | None = None
    average_return_percent: float | None = None
    average_abs_return_percent: float | None = None


class AnalysisWeekdayStatOut(BaseModel):
    weekday: int
    label: str
    market_sample_count: int
    market_average_daily_return_percent: float | None = None
    signal_count: int
    signal_day_average_return_percent: float | None = None
    average_return_1d_percent: float | None = None
    average_return_3d_percent: float | None = None
    average_return_5d_percent: float | None = None
    interaction_effect_1d_percent: float | None = None
    major_sq_week_market_sample_count: int = 0
    major_sq_week_market_average_daily_return_percent: float | None = None
    major_sq_week_signal_count: int = 0
    major_sq_week_average_return_1d_percent: float | None = None
    major_sq_week_average_return_3d_percent: float | None = None
    major_sq_week_average_return_5d_percent: float | None = None
    major_sq_week_interaction_effect_1d_percent: float | None = None


class AnalysisRuleOut(BaseModel):
    side: str
    name: str
    condition: str
    description: str
    primary_category: str | None = None
    categories: list[str] = Field(default_factory=list)
    supported: bool
    current_signal_count: int
    backtest: AnalysisBacktestOut
    weekday_stats: list[AnalysisWeekdayStatOut] = Field(default_factory=list)


class AnalysisCategoryOut(BaseModel):
    side: str
    name: str
    category_a: str | None = None
    category_b: str | None = None
    relation: str | None = None
    matrix_weight: float | None = None
    rule_count: int
    current_signal_count: int
    backtest: AnalysisBacktestOut
    baseline_backtest: AnalysisBacktestOut | None = None
    interaction_effect_return_percent: float | None = None
    weekday_stats: list[AnalysisWeekdayStatOut] = Field(default_factory=list)


class AnalysisSignalOut(BaseModel):
    symbol_id: int
    ticker: str
    name: str
    side: str
    rule_name: str
    primary_category: str | None = None
    categories: list[str] = Field(default_factory=list)
    date: str
    close: float
    reason: str
    rsi_14: float | None = None
    rsi_2: float | None = None


class InvestmentAnalysisOut(BaseModel):
    rules: list[AnalysisRuleOut]
    categories: list[AnalysisCategoryOut] = Field(default_factory=list)
    category_interactions: dict[str, dict[str, float]] = Field(default_factory=dict)
    signals: list[AnalysisSignalOut]
    generated_at: str | None = None
    horizon_days: int
    lookback_years: int = 5
    status: str = "not_calculated"
    last_started_at: str | None = None
    last_finished_at: str | None = None
    error: str | None = None


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
    quantity: float | None = Field(default=None, gt=0)
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


class TaskTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#7dd3fc", min_length=4, max_length=20)


class TaskTagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, min_length=4, max_length=20)
    hidden: bool | None = None


class TaskTagOut(BaseModel):
    id: int
    name: str
    color: str
    hidden: bool
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    status: str = Field(default="todo", pattern="^(todo|doing|done)$")
    due_date: str | None = Field(default=None, max_length=20)
    duration_days: int | None = Field(default=None, ge=0, le=36500)
    tag_ids: list[int] = Field(default_factory=list)
    details: str = Field(default="", max_length=5000)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    status: str | None = Field(default=None, pattern="^(todo|doing|done)$")
    due_date: str | None = Field(default=None, max_length=20)
    duration_days: int | None = Field(default=None, ge=0, le=36500)
    tag_ids: list[int] | None = None
    details: str | None = Field(default=None, max_length=5000)


class TaskOut(BaseModel):
    id: int
    title: str
    status: str
    due_date: str | None = None
    duration_days: int | None = None
    tags: list[TaskTagOut]
    details: str
    completed_at: str | None = None
    created_at: str
    updated_at: str


class HouseholdTransactionUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=80)
    memo: str | None = Field(default=None, max_length=500)
    excluded: bool | None = None


class HouseholdTransactionOut(BaseModel):
    id: int
    transacted_at: str
    amount: int
    direction: str
    category: str
    merchant: str
    description: str
    source_type: str
    balance_after: int | None = None
    memo: str
    excluded: bool
    created_at: str
    updated_at: str


class HouseholdMonthlySummaryOut(BaseModel):
    month: str
    income: int
    expense: int
    net: int
    savings_rate_percent: float | None = None


class HouseholdCategorySummaryOut(BaseModel):
    category: str
    expense: int
    transaction_count: int
    share_percent: float | None = None


class HouseholdAssetPointOut(BaseModel):
    date: str
    balance: int


class HouseholdImportOut(BaseModel):
    imported: int
    skipped: int
    excluded: int = 0


class HouseholdAnalysisOut(BaseModel):
    transactions: list[HouseholdTransactionOut]
    monthly: list[HouseholdMonthlySummaryOut]
    categories: list[HouseholdCategorySummaryOut]
    asset_points: list[HouseholdAssetPointOut] = Field(default_factory=list)
    total_income: int
    total_expense: int
    net: int
    average_monthly_expense: float
    largest_expense: HouseholdTransactionOut | None = None
