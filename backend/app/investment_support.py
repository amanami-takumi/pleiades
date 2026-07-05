from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean, pstdev

from .database import get_db
from .models import (
    AnalysisBacktestOut,
    AnalysisCategoryOut,
    AnalysisRuleOut,
    AnalysisSignalOut,
    AnalysisWeekdayStatOut,
    InvestmentAnalysisOut,
    SymbolOut,
)


RULES_PATH = Path(__file__).resolve().parents[2] / "売買ルール.csv"
CATEGORIZED_RULES_PATH = Path(__file__).resolve().parents[2] / "quant_rules_categorized.csv"
CATEGORY_INTERACTION_PATH = Path(__file__).resolve().parents[2] / "category_interaction_matrix.csv"
WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]


@dataclass(frozen=True)
class PriceRow:
    date: str
    open: float | None
    close: float
    high: float | None
    low: float | None
    volume: int | None


@dataclass(frozen=True)
class RuleDefinition:
    key: str
    side: str
    name: str
    condition: str
    description: str
    primary_category: str | None = None
    categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class CategoryInteractionDefinition:
    label: str
    weight: float


@dataclass
class BacktestAccumulator:
    side: str
    backtest_returns: list[float]
    correct_count: int
    current_signal_count: int
    signal_day_returns_by_weekday: dict[int, list[float]]
    signal_returns_by_weekday: dict[int, dict[int, list[float]]]
    major_sq_week_signal_returns_by_weekday: dict[int, dict[int, list[float]]]

    @classmethod
    def create(cls, side: str) -> "BacktestAccumulator":
        return cls(
            side=side,
            backtest_returns=[],
            correct_count=0,
            current_signal_count=0,
            signal_day_returns_by_weekday=defaultdict(list),
            signal_returns_by_weekday=defaultdict(lambda: defaultdict(list)),
            major_sq_week_signal_returns_by_weekday=defaultdict(lambda: defaultdict(list)),
        )

    def add_backtest_signal(self, rows: list[PriceRow], index: int, horizon_days: int) -> None:
        future_return = (rows[index + horizon_days].close - rows[index].close) / rows[index].close * 100
        expected_return = future_return if self.side == "買い" else -future_return
        self.backtest_returns.append(expected_return)
        if expected_return > 0:
            self.correct_count += 1
        entry_weekday = weekday_for(rows[index].date)
        if index > 0:
            signal_day_return = (rows[index].close - rows[index - 1].close) / rows[index - 1].close * 100
            self.signal_day_returns_by_weekday[entry_weekday].append(signal_day_return)
        for forward_days in (1, 3, 5):
            if index + forward_days < len(rows):
                forward_return = (rows[index + forward_days].close - rows[index].close) / rows[index].close * 100
                expected_forward_return = forward_return if self.side == "買い" else -forward_return
                self.signal_returns_by_weekday[entry_weekday][forward_days].append(expected_forward_return)
                if is_major_sq_week(rows[index].date):
                    self.major_sq_week_signal_returns_by_weekday[entry_weekday][forward_days].append(
                        expected_forward_return
                    )

    def to_backtest(self) -> AnalysisBacktestOut:
        signals = len(self.backtest_returns)
        return AnalysisBacktestOut(
            signals=signals,
            correct=self.correct_count,
            accuracy_percent=(self.correct_count / signals * 100) if signals else None,
            average_return_percent=mean(self.backtest_returns) if self.backtest_returns else None,
            average_abs_return_percent=mean(abs(value) for value in self.backtest_returns)
            if self.backtest_returns
            else None,
        )


@dataclass(frozen=True)
class IndicatorSeries:
    ma5: list[float | None]
    ma20: list[float | None]
    ma60: list[float | None]
    ma120: list[float | None]
    ma200: list[float | None]
    bb_upper_1: list[float | None]
    bb_upper_2: list[float | None]
    bb_lower_1: list[float | None]
    bb_lower_2: list[float | None]
    bb_width: list[float | None]
    bb_width_rank_120: list[float | None]
    bb_width_rank_120_high: list[float | None]
    percent_b: list[float | None]
    avg_volume20: list[float | None]
    macd: list[float | None]
    macd_signal: list[float | None]
    macd_hist: list[float | None]


def load_rule_definitions() -> list[RuleDefinition]:
    path = CATEGORIZED_RULES_PATH if CATEGORIZED_RULES_PATH.exists() else RULES_PATH
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    return [
        RuleDefinition(
            key=f"{row.get('区分', '')}:{row.get('ルール名', '')}",
            side=row.get("区分", ""),
            name=row.get("ルール名", ""),
            condition=row.get("売買条件例", ""),
            description=row.get("狙い・特徴", ""),
            primary_category=(row.get("主カテゴリ") or None),
            categories=tuple(split_categories(row.get("カテゴリタグ", ""))),
        )
        for row in rows
        if row.get("区分") and row.get("ルール名")
    ]


def split_categories(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def load_category_interaction_matrix() -> dict[str, dict[str, CategoryInteractionDefinition]]:
    if not CATEGORY_INTERACTION_PATH.exists():
        return {}
    with CATEGORY_INTERACTION_PATH.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    interactions: dict[str, dict[str, CategoryInteractionDefinition]] = {}
    for row in rows:
        category = row.get("カテゴリA", "")
        if not category:
            continue
        interactions[category] = {
            other: CategoryInteractionDefinition(label=text, weight=category_interaction_weight(text))
            for other, text in row.items()
            if other and other != "カテゴリA" and text
        }
    return interactions


def category_interaction_weights(
    matrix: dict[str, dict[str, CategoryInteractionDefinition]],
) -> dict[str, dict[str, float]]:
    return {
        category: {other: definition.weight for other, definition in others.items()}
        for category, others in matrix.items()
    }


def category_interaction_weight(text: str) -> float:
    if "強い衝突" in text or "方向衝突" in text:
        return -0.5
    if "衝突注意" in text:
        return -0.25
    if "弱い衝突" in text:
        return -0.15
    if "同系統" in text:
        return -0.1
    if "近接" in text:
        return -0.05
    if "補完" in text:
        return 0.25
    if "条件付き" in text:
        return 0.05
    if "弱い関連" in text:
        return 0.03
    return 0.0


def build_investment_analysis(
    symbols: list[SymbolOut],
    horizon_days: int,
    lookback_years: int,
) -> InvestmentAnalysisOut:
    backtest_days = lookback_years * 260
    histories = load_price_histories(backtest_days + horizon_days + 260)
    rule_definitions = load_rule_definitions()
    if not rule_definitions:
        return InvestmentAnalysisOut(
            rules=[],
            categories=[],
            signals=[],
            generated_at=None,
            horizon_days=horizon_days,
            lookback_years=lookback_years,
        )

    symbol_by_id = {symbol.id: symbol for symbol in symbols}
    momentum_scores = build_momentum_scores(histories)
    market_returns_by_weekday = build_market_returns_by_weekday(histories)
    major_sq_week_market_returns_by_weekday = build_market_returns_by_weekday(histories, major_sq_week_only=True)
    category_interaction_matrix = load_category_interaction_matrix()
    category_interactions = category_interaction_weights(category_interaction_matrix)
    matrix_categories = list(category_interaction_matrix.keys())
    rules: list[AnalysisRuleOut] = []
    current_signals: list[AnalysisSignalOut] = []
    category_accumulators: dict[tuple[str, str], BacktestAccumulator] = {}
    category_rule_names: dict[tuple[str, str], set[str]] = defaultdict(set)
    category_backtest_seen: set[tuple[str, str, int, str]] = set()
    category_current_seen: set[tuple[str, str, int]] = set()
    category_events_by_symbol_date: dict[
        tuple[int, str], dict[tuple[str, str], tuple[list[PriceRow], int]]
    ] = defaultdict(dict)
    current_categories_by_symbol: dict[int, set[tuple[str, str]]] = defaultdict(set)

    for definition in rule_definitions:
        rule_accumulator = BacktestAccumulator.create(definition.side)
        current_count = 0
        primary_category = definition.primary_category or "未分類"
        category_key = (definition.side, primary_category)
        category_rule_names[category_key].add(definition.name)
        category_accumulator = category_accumulators.setdefault(
            category_key,
            BacktestAccumulator.create(definition.side),
        )
        categories = tuple(dict.fromkeys((primary_category, *definition.categories)))

        for symbol_id, rows in histories.items():
            symbol = symbol_by_id.get(symbol_id)
            if symbol is None or len(rows) < horizon_days + 2:
                continue
            indicators = build_indicators(rows)
            first_backtest_index = max(0, len(rows) - backtest_days)
            for index in range(first_backtest_index, len(rows) - horizon_days):
                result = evaluate_rule(definition.name, symbol_id, rows, index, momentum_scores, indicators)
                if result is None:
                    continue
                rule_accumulator.add_backtest_signal(rows, index, horizon_days)
                category_seen_key = (definition.side, primary_category, symbol_id, rows[index].date)
                if category_seen_key not in category_backtest_seen:
                    category_backtest_seen.add(category_seen_key)
                    category_accumulator.add_backtest_signal(rows, index, horizon_days)
                    category_events_by_symbol_date[(symbol_id, rows[index].date)][
                        (definition.side, primary_category)
                    ] = (rows, index)

            latest_index = len(rows) - 1
            result = evaluate_rule(definition.name, symbol_id, rows, latest_index, momentum_scores, indicators)
            if result is not None:
                current_count += 1
                category_current_key = (definition.side, primary_category, symbol.id)
                if category_current_key not in category_current_seen:
                    category_current_seen.add(category_current_key)
                    category_accumulator.current_signal_count += 1
                    current_categories_by_symbol[symbol.id].add((definition.side, primary_category))
                current_signals.append(
                    AnalysisSignalOut(
                        symbol_id=symbol.id,
                        ticker=symbol.ticker,
                        name=symbol.name,
                        side=definition.side,
                        rule_name=definition.name,
                        primary_category=primary_category,
                        categories=list(categories),
                        date=rows[latest_index].date,
                        close=rows[latest_index].close,
                        reason=result,
                        rsi_14=rsi(rows, latest_index, 14),
                        rsi_2=rsi(rows, latest_index, 2),
                    )
                )

        rules.append(
            AnalysisRuleOut(
                side=definition.side,
                name=definition.name,
                condition=definition.condition,
                description=definition.description,
                primary_category=primary_category,
                categories=list(categories),
                supported=is_supported_rule(definition.name),
                current_signal_count=current_count,
                backtest=rule_accumulator.to_backtest(),
                weekday_stats=build_weekday_stats(
                    definition.side,
                    market_returns_by_weekday,
                    major_sq_week_market_returns_by_weekday,
                    rule_accumulator.signal_day_returns_by_weekday,
                    rule_accumulator.signal_returns_by_weekday,
                    rule_accumulator.major_sq_week_signal_returns_by_weekday,
                ),
            )
        )

    categories = build_category_interaction_backtests(
        matrix_categories,
        category_interaction_matrix,
        category_accumulators,
        category_rule_names,
        category_events_by_symbol_date,
        current_categories_by_symbol,
        market_returns_by_weekday,
        major_sq_week_market_returns_by_weekday,
        horizon_days,
    )
    categories.sort(key=lambda category: (category.side != "買い", category.name))
    current_signals.sort(key=lambda signal: (signal.side != "買い", signal.rule_name, signal.ticker))
    generated_at = max((rows[-1].date for rows in histories.values() if rows), default=None)
    return InvestmentAnalysisOut(
        rules=rules,
        categories=categories,
        category_interactions=category_interactions,
        signals=current_signals,
        generated_at=generated_at,
        horizon_days=horizon_days,
        lookback_years=lookback_years,
        status="succeeded",
    )


def build_category_interaction_backtests(
    matrix_categories: list[str],
    category_interaction_matrix: dict[str, dict[str, CategoryInteractionDefinition]],
    category_accumulators: dict[tuple[str, str], BacktestAccumulator],
    category_rule_names: dict[tuple[str, str], set[str]],
    category_events_by_symbol_date: dict[tuple[int, str], dict[tuple[str, str], tuple[list[PriceRow], int]]],
    current_categories_by_symbol: dict[int, set[tuple[str, str]]],
    market_returns_by_weekday: dict[int, list[float]],
    major_sq_week_market_returns_by_weekday: dict[int, list[float]],
    horizon_days: int,
) -> list[AnalysisCategoryOut]:
    if not matrix_categories:
        return [
            AnalysisCategoryOut(
                side=side,
                name=category,
                category_a=category,
                rule_count=len(category_rule_names[(side, category)]),
                current_signal_count=accumulator.current_signal_count,
                backtest=accumulator.to_backtest(),
                weekday_stats=build_weekday_stats(
                    side,
                    market_returns_by_weekday,
                    major_sq_week_market_returns_by_weekday,
                    accumulator.signal_day_returns_by_weekday,
                    accumulator.signal_returns_by_weekday,
                    accumulator.major_sq_week_signal_returns_by_weekday,
                ),
            )
            for (side, category), accumulator in category_accumulators.items()
        ]

    categories: list[AnalysisCategoryOut] = []
    for side in ("買い", "売り"):
        for category_a in matrix_categories:
            baseline_accumulator = category_accumulators.get((side, category_a), BacktestAccumulator.create(side))
            baseline_backtest = baseline_accumulator.to_backtest()
            for category_b in matrix_categories:
                interaction_definition = category_interaction_matrix.get(category_a, {}).get(category_b)
                accumulator = BacktestAccumulator.create(side)
                current_signal_count = 0
                for categories_for_symbol in current_categories_by_symbol.values():
                    if (side, category_a) not in categories_for_symbol:
                        continue
                    if any(category == category_b for _, category in categories_for_symbol):
                        current_signal_count += 1
                for event_categories in category_events_by_symbol_date.values():
                    event = event_categories.get((side, category_a))
                    if event is None:
                        continue
                    if not any(category == category_b for _, category in event_categories):
                        continue
                    rows, index = event
                    accumulator.add_backtest_signal(rows, index, horizon_days)
                backtest = accumulator.to_backtest()
                baseline_average = baseline_backtest.average_return_percent
                interaction_average = backtest.average_return_percent
                categories.append(
                    AnalysisCategoryOut(
                        side=side,
                        name=f"{category_a} × {category_b}",
                        category_a=category_a,
                        category_b=category_b,
                        relation=interaction_definition.label if interaction_definition else None,
                        matrix_weight=interaction_definition.weight if interaction_definition else None,
                        rule_count=len(category_rule_names[(side, category_a)]),
                        current_signal_count=current_signal_count,
                        backtest=backtest,
                        baseline_backtest=baseline_backtest,
                        interaction_effect_return_percent=(
                            interaction_average - baseline_average
                            if interaction_average is not None and baseline_average is not None
                            else None
                        ),
                        weekday_stats=build_weekday_stats(
                            side,
                            market_returns_by_weekday,
                            major_sq_week_market_returns_by_weekday,
                            accumulator.signal_day_returns_by_weekday,
                            accumulator.signal_returns_by_weekday,
                            accumulator.major_sq_week_signal_returns_by_weekday,
                        ),
                    )
                )
    return categories


def build_market_returns_by_weekday(
    histories: dict[int, list[PriceRow]],
    major_sq_week_only: bool = False,
) -> dict[int, list[float]]:
    returns_by_weekday: dict[int, list[float]] = defaultdict(list)
    for rows in histories.values():
        for index in range(1, len(rows)):
            if major_sq_week_only and not is_major_sq_week(rows[index].date):
                continue
            prior = rows[index - 1].close
            if prior <= 0:
                continue
            returns_by_weekday[weekday_for(rows[index].date)].append((rows[index].close - prior) / prior * 100)
    return returns_by_weekday


def build_weekday_stats(
    side: str,
    market_returns_by_weekday: dict[int, list[float]],
    major_sq_week_market_returns_by_weekday: dict[int, list[float]],
    signal_day_returns_by_weekday: dict[int, list[float]],
    signal_returns_by_weekday: dict[int, dict[int, list[float]]],
    major_sq_week_signal_returns_by_weekday: dict[int, dict[int, list[float]]],
) -> list[AnalysisWeekdayStatOut]:
    market_all = [
        value
        for weekday_returns in market_returns_by_weekday.values()
        for value in weekday_returns
    ]
    signal_all_1d = [
        value
        for weekday_returns in signal_returns_by_weekday.values()
        for value in weekday_returns.get(1, [])
    ]
    market_all_average = mean_or_none(market_all)
    if side == "売り" and market_all_average is not None:
        market_all_average = -market_all_average
    signal_all_average = mean_or_none(signal_all_1d)
    major_sq_week_market_all = [
        value
        for weekday_returns in major_sq_week_market_returns_by_weekday.values()
        for value in weekday_returns
    ]
    major_sq_week_signal_all_1d = [
        value
        for weekday_returns in major_sq_week_signal_returns_by_weekday.values()
        for value in weekday_returns.get(1, [])
    ]
    major_sq_week_market_all_average = mean_or_none(major_sq_week_market_all)
    if side == "売り" and major_sq_week_market_all_average is not None:
        major_sq_week_market_all_average = -major_sq_week_market_all_average
    major_sq_week_signal_all_average = mean_or_none(major_sq_week_signal_all_1d)
    stats: list[AnalysisWeekdayStatOut] = []
    for weekday in range(5):
        market_returns = market_returns_by_weekday.get(weekday, [])
        market_average = mean_or_none(market_returns)
        if side == "売り" and market_average is not None:
            market_average = -market_average
        major_sq_week_market_returns = major_sq_week_market_returns_by_weekday.get(weekday, [])
        major_sq_week_market_average = mean_or_none(major_sq_week_market_returns)
        if side == "売り" and major_sq_week_market_average is not None:
            major_sq_week_market_average = -major_sq_week_market_average
        signal_average_1d = mean_or_none(signal_returns_by_weekday.get(weekday, {}).get(1, []))
        major_sq_week_signal_average_1d = mean_or_none(
            major_sq_week_signal_returns_by_weekday.get(weekday, {}).get(1, [])
        )
        interaction_effect = None
        if signal_average_1d is not None and market_average is not None:
            interaction_effect = signal_average_1d - market_average
            if signal_all_average is not None and market_all_average is not None:
                interaction_effect -= signal_all_average - market_all_average
        major_sq_week_interaction_effect = None
        if major_sq_week_signal_average_1d is not None and major_sq_week_market_average is not None:
            major_sq_week_interaction_effect = major_sq_week_signal_average_1d - major_sq_week_market_average
            if major_sq_week_signal_all_average is not None and major_sq_week_market_all_average is not None:
                major_sq_week_interaction_effect -= major_sq_week_signal_all_average - major_sq_week_market_all_average
        stats.append(
            AnalysisWeekdayStatOut(
                weekday=weekday,
                label=WEEKDAY_LABELS[weekday],
                market_sample_count=len(market_returns),
                market_average_daily_return_percent=market_average,
                signal_count=len(signal_returns_by_weekday.get(weekday, {}).get(1, [])),
                signal_day_average_return_percent=mean_or_none(signal_day_returns_by_weekday.get(weekday, [])),
                average_return_1d_percent=signal_average_1d,
                average_return_3d_percent=mean_or_none(signal_returns_by_weekday.get(weekday, {}).get(3, [])),
                average_return_5d_percent=mean_or_none(signal_returns_by_weekday.get(weekday, {}).get(5, [])),
                interaction_effect_1d_percent=interaction_effect,
                major_sq_week_market_sample_count=len(major_sq_week_market_returns),
                major_sq_week_market_average_daily_return_percent=major_sq_week_market_average,
                major_sq_week_signal_count=len(major_sq_week_signal_returns_by_weekday.get(weekday, {}).get(1, [])),
                major_sq_week_average_return_1d_percent=major_sq_week_signal_average_1d,
                major_sq_week_average_return_3d_percent=mean_or_none(
                    major_sq_week_signal_returns_by_weekday.get(weekday, {}).get(3, [])
                ),
                major_sq_week_average_return_5d_percent=mean_or_none(
                    major_sq_week_signal_returns_by_weekday.get(weekday, {}).get(5, [])
                ),
                major_sq_week_interaction_effect_1d_percent=major_sq_week_interaction_effect,
            )
        )
    return stats


def load_price_histories(max_rows_per_symbol: int) -> dict[int, list[PriceRow]]:
    histories: dict[int, list[PriceRow]] = defaultdict(list)
    with get_db() as db:
        rows = db.execute(
            """
            WITH ranked AS (
              SELECT
                symbol_id,
                date,
                open,
                close,
                high,
                low,
                volume,
                ROW_NUMBER() OVER (PARTITION BY symbol_id ORDER BY date DESC) AS rn
              FROM prices
              WHERE close IS NOT NULL AND close > 0
            )
            SELECT symbol_id, date, open, close, high, low, volume
            FROM ranked
            WHERE rn <= ?
            ORDER BY symbol_id, date
            """,
            (max_rows_per_symbol,),
        ).fetchall()
    for row in rows:
        histories[row["symbol_id"]].append(
            PriceRow(
                date=row["date"],
                open=row["open"],
                close=row["close"],
                high=row["high"],
                low=row["low"],
                volume=row["volume"],
            )
        )
    return histories


def weekday_for(value: str) -> int:
    return date.fromisoformat(value).weekday()


def is_major_sq_week(value: str) -> bool:
    target = date.fromisoformat(value)
    if target.month not in {3, 6, 9, 12}:
        return False
    second_friday = nth_weekday(target.year, target.month, weekday=4, occurrence=2)
    return 0 <= (second_friday - target).days <= 4


def nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    current = date(year, month, 1)
    offset = (weekday - current.weekday()) % 7
    return date(year, month, 1 + offset + (occurrence - 1) * 7)


def mean_or_none(values: list[float]) -> float | None:
    return mean(values) if values else None


def build_indicators(rows: list[PriceRow]) -> IndicatorSeries:
    closes = [row.close for row in rows]
    volumes = [row.volume for row in rows]
    ma5 = rolling_mean_values(closes, 5)
    ma20 = rolling_mean_values(closes, 20)
    ma60 = rolling_mean_values(closes, 60)
    ma120 = rolling_mean_values(closes, 120)
    ma200 = rolling_mean_values(closes, 200)
    std20 = rolling_std_values(closes, 20)
    bb_upper_1 = combine_band(ma20, std20, 1)
    bb_upper_2 = combine_band(ma20, std20, 2)
    bb_lower_1 = combine_band(ma20, std20, -1)
    bb_lower_2 = combine_band(ma20, std20, -2)
    bb_width = [
        ((upper - lower) / center) if upper is not None and lower is not None and center else None
        for upper, lower, center in zip(bb_upper_2, bb_lower_2, ma20)
    ]
    ema12 = ema_values(closes, 12)
    ema26 = ema_values(closes, 26)
    macd = [
        (short - long) if short is not None and long is not None else None
        for short, long in zip(ema12, ema26)
    ]
    macd_signal = ema_optional_values(macd, 9)
    macd_hist = [
        (value - signal) if value is not None and signal is not None else None
        for value, signal in zip(macd, macd_signal)
    ]
    return IndicatorSeries(
        ma5=ma5,
        ma20=ma20,
        ma60=ma60,
        ma120=ma120,
        ma200=ma200,
        bb_upper_1=bb_upper_1,
        bb_upper_2=bb_upper_2,
        bb_lower_1=bb_lower_1,
        bb_lower_2=bb_lower_2,
        bb_width=bb_width,
        bb_width_rank_120=rolling_percentile_rank(bb_width, 120),
        bb_width_rank_120_high=rolling_percentile_rank(bb_width, 120, reverse=True),
        percent_b=[
            ((close - lower) / (upper - lower))
            if upper is not None and lower is not None and upper != lower
            else None
            for close, lower, upper in zip(closes, bb_lower_2, bb_upper_2)
        ],
        avg_volume20=rolling_mean_optional_values(volumes, 20),
        macd=macd,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
    )


def rolling_mean_values(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= period:
            total -= values[index - period]
        if index >= period - 1:
            result[index] = total / period
    return result


def rolling_mean_optional_values(values: list[int | None], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        if all(value is not None for value in window):
            result[index] = mean(value for value in window if value is not None)
    return result


def rolling_std_values(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        result[index] = pstdev(values[index - period + 1 : index + 1])
    return result


def combine_band(center: list[float | None], deviation: list[float | None], multiplier: int) -> list[float | None]:
    return [
        (center_value + deviation_value * multiplier)
        if center_value is not None and deviation_value is not None
        else None
        for center_value, deviation_value in zip(center, deviation)
    ]


def rolling_percentile_rank(
    values: list[float | None],
    period: int,
    reverse: bool = False,
) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        current = values[index]
        if current is None:
            continue
        window = [value for value in values[index - period + 1 : index + 1] if value is not None]
        if not window:
            continue
        if reverse:
            result[index] = sum(1 for value in window if value >= current) / len(window) * 100
        else:
            result[index] = sum(1 for value in window if value <= current) / len(window) * 100
    return result


def ema_values(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    multiplier = 2 / (period + 1)
    ema = mean(values[:period])
    result[period - 1] = ema
    for index in range(period, len(values)):
        ema = (values[index] - ema) * multiplier + ema
        result[index] = ema
    return result


def ema_optional_values(values: list[float | None], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    available = [(index, value) for index, value in enumerate(values) if value is not None]
    if len(available) < period:
        return result
    multiplier = 2 / (period + 1)
    start_index = available[period - 1][0]
    ema = mean(value for _, value in available[:period] if value is not None)
    result[start_index] = ema
    for index, value in available[period:]:
        if value is None:
            continue
        ema = (value - ema) * multiplier + ema
        result[index] = ema
    return result


def build_momentum_scores(histories: dict[int, list[PriceRow]]) -> dict[str, dict[int, float]]:
    scores_by_date: dict[str, dict[int, float]] = defaultdict(dict)
    for symbol_id, rows in histories.items():
        for index in range(147, len(rows)):
            recent = rows[index - 21].close
            past = rows[index - 147].close
            if past > 0:
                scores_by_date[rows[index].date][symbol_id] = (recent - past) / past * 100
    return scores_by_date


def evaluate_rule(
    name: str,
    symbol_id: int,
    rows: list[PriceRow],
    index: int,
    momentum_scores: dict[str, dict[int, float]],
    indicators: IndicatorSeries,
) -> str | None:
    close = rows[index].close
    ma20 = indicators.ma20[index]
    ma60 = indicators.ma60[index]
    ma120 = indicators.ma120[index]
    ma200 = indicators.ma200[index]
    upper1 = indicators.bb_upper_1[index]
    upper2 = indicators.bb_upper_2[index]
    lower1 = indicators.bb_lower_1[index]
    lower2 = indicators.bb_lower_2[index]
    macd = indicators.macd[index]
    signal = indicators.macd_signal[index]
    hist = indicators.macd_hist[index]

    if name == "移動平均トレンドフォロー":
        if ma200 and ma20 and ma60 and close > ma200 and ma20 > ma60:
            return f"終値が200日MAを上回り、20日MAが60日MAを上回っています"
    elif name == "クロスセクション・モメンタム":
        score = momentum_percentile(momentum_scores, rows[index].date, symbol_id)
        if score is not None and score >= 80:
            return "6か月モメンタムが同日比較の上位20%です"
    elif name == "高値ブレイクアウト":
        high20 = max_high(rows, index - 1, 20)
        high55 = max_high(rows, index - 1, 55)
        if (high20 and close > high20) or (high55 and close > high55):
            return "終値が過去20日または55日の高値を上回っています"
    elif name == "上昇トレンド中のRSI押し目買い":
        rsi14 = rsi(rows, index, 14)
        rsi2 = rsi(rows, index, 2)
        if ma200 and close > ma200 and ((rsi14 is not None and rsi14 < 30) or (rsi2 is not None and rsi2 < 10)):
            return "200日MA上の上昇基調でRSIが売られすぎ圏です"
    elif name == "ボラティリティ収縮後の上放れ":
        band = bollinger(rows, index, 20)
        if band and close > band[1]:
            width_rank = bollinger_width_percentile(rows, index, 120)
            if width_rank is not None and width_rank <= 20:
                return "ボリンジャーバンド幅が低位で、終値が上側バンドを上抜けています"
    elif name == "短期リバーサル買い":
        ret5 = period_return(rows, index, 5)
        if ma200 and close > ma200 and ret5 is not None and ret5 <= -5:
            avg_volume = average_volume(rows, index - 1, 20)
            volume = rows[index].volume
            if avg_volume and volume and volume > avg_volume * 1.5:
                return "長期トレンド維持中に短期下落と出来高急増が発生しています"
    elif name == "移動平均デッドクロス・トレンド崩れ":
        if ma20 and ma60 and ma200 and (ma20 < ma60 or close < ma200):
            return "20日MAが60日MAを下回る、または終値が200日MAを下回っています"
    elif name == "モメンタム劣化売り":
        score = momentum_percentile(momentum_scores, rows[index].date, symbol_id)
        if score is not None and score <= 50:
            return "6か月モメンタムが同日比較で中央以下です"
    elif name == "Donchian・ATRトレーリングストップ":
        low20 = min_low(rows, index - 1, 20)
        atr14 = atr(rows, index, 14)
        high_since = max_high(rows, index, 55)
        if (low20 and close < low20) or (atr14 and high_since and close < high_since - atr14 * 2):
            return "終値が過去20日安値割れ、または直近高値から2ATR以上下落しています"
    elif name == "RSI過熱売り":
        rsi14 = rsi(rows, index, 14)
        if rsi14 is not None and rsi14 > 70:
            return "RSI(14)が70を上回っています"
    elif name == "ボリンジャーバンド上抜け失敗売り":
        band = bollinger(rows, index, 20)
        prior_break = any(
            (prior_band := bollinger(rows, prior, 20)) is not None and rows[prior].close > prior_band[1]
            for prior in range(max(0, index - 3), index)
        )
        if band and prior_break and close < band[1]:
            return "数日内の上側バンド上抜け後、終値がバンド内に戻っています"
    elif name == "時間切れ売り・期待値未達売り":
        ret20 = period_return(rows, index, 20)
        if ret20 is not None and ret20 < 0:
            return "20営業日リターンがマイナスです"
    elif name == "BBスクイーズ上放れ":
        avg_volume = indicators.avg_volume20[index]
        volume = rows[index].volume
        if (
            indicators.bb_width_rank_120[index] is not None
            and indicators.bb_width_rank_120[index] <= 20
            and upper2
            and close > upper2
            and avg_volume
            and volume
            and volume > avg_volume
        ):
            return "BB幅が過去120日下位20%で、終値が+2σを上抜け、出来高が20日平均を上回っています"
    elif name == "BB上限ブレイク継続":
        if index > 0 and upper1 and indicators.bb_upper_2[index - 1] and close >= upper1:
            prior_ma20 = indicators.ma20[index - 1]
            ma20_5ago = indicators.ma20[index - 6] if index >= 6 else None
            if rows[index - 1].close > indicators.bb_upper_2[index - 1] and prior_ma20 and ma20_5ago and prior_ma20 > ma20_5ago:
                return "前日に+2σを上抜け、当日も+1σ以上で推移しています"
    elif name == "BB中央線押し目買い":
        high10 = max_high(rows, index - 1, 10)
        if ma20 and high10 and index >= 5 and min_distance_to_ma20(rows, indicators, index, 5) <= 0.02:
            if indicators.ma20[index - 1] is not None and close > ma20 and ma20 > indicators.ma20[index - 1] and close > high10:
                return "20日MA付近への押し目後、20日MAを上回り直近高値を更新しています"
    elif name == "BB下限フェイクアウト反発":
        if index > 0 and indicators.bb_lower_2[index - 1] and indicators.bb_lower_1[index - 1]:
            prior = rows[index - 1]
            if prior.low and prior.low < indicators.bb_lower_2[index - 1] and prior.close > indicators.bb_lower_1[index - 1]:
                if close > (prior.high if prior.high is not None else prior.close):
                    return "前日に-2σを一時割れ後、当日に前日高値を上回って反発しています"
    elif name == "BB幅拡大トレンド開始":
        if index > 0 and indicators.bb_width[index] and indicators.bb_width[index - 1] and upper1 and ma20 and ma60:
            if indicators.bb_width[index] > indicators.bb_width[index - 1] and close > upper1 and ma20 > ma60:
                return "BB幅が前日比で拡大し、終値が+1σを上回り20日MAが60日MAを上回っています"
    elif name == "BBパーセントB急回復":
        if indicators.percent_b[index] is not None and indicators.percent_b[index] > 0.8 and ma20 and close > ma20:
            recent_low_b = [
                value for value in indicators.percent_b[max(0, index - 2) : index] if value is not None and value < 0.2
            ]
            if recent_low_b:
                return "%Bが0.2未満から2日以内に0.8超へ回復し、終値が20日MAを上回っています"
    elif name == "BB上限張り付き":
        if ma20 and close >= ma20 and count_closes_above(rows, indicators.bb_upper_1, index, 5) >= 3:
            if all(row.close >= ma for row, ma in zip(rows[max(0, index - 4) : index + 1], indicators.ma20[max(0, index - 4) : index + 1]) if ma is not None):
                return "過去5日のうち3日以上で終値が+1σ以上、かつ20日MAを維持しています"
    elif name == "BB収縮後のギャップ上放れ":
        previous_high = rows[index - 1].high if index > 0 else None
        if (
            index > 0
            and indicators.bb_width_rank_120[index] is not None
            and indicators.bb_width_rank_120[index] <= 25
            and previous_high
            and rows[index].open
            and rows[index].open > previous_high
            and upper2
            and close > upper2
        ):
            return "BB幅が低位で、当日始値が前日高値を上回り、終値が+2σを上抜けています"
    elif name == "BB上限失速利確":
        if index > 0 and indicators.bb_upper_2[index - 1] and upper1:
            previous_high = rows[index - 1].high if rows[index - 1].high is not None else rows[index - 1].close
            today_high = rows[index].high if rows[index].high is not None else close
            if rows[index - 1].close > indicators.bb_upper_2[index - 1] and close < upper1 and today_high <= previous_high:
                return "前日の+2σ上抜け後、終値が+1σを下回り高値更新に失敗しています"
    elif name == "BB中央線割れ手仕舞い":
        if ma20 and close < ma20 and index > 0 and indicators.ma20[index - 1] and ma20 <= indicators.ma20[index - 1]:
            return "終値が20日MAを下回り、20日MAが横ばいまたは下向きです"
    elif name == "BB幅急拡大後の反落":
        if indicators.bb_width_rank_120_high[index] is not None and indicators.bb_width_rank_120_high[index] <= 20 and upper1:
            if close < upper1 and index > 0 and close < rows[index - 1].close:
                return "BB幅が過去120日上位20%で、終値が+1σを下回り前日比マイナスです"
    elif name == "BB下方ブレイク回避":
        if (
            lower2
            and ma20
            and index > 0
            and indicators.ma20[index - 1] is not None
            and indicators.bb_width[index] is not None
            and indicators.bb_width[index - 1] is not None
        ):
            if close < lower2 and ma20 < indicators.ma20[index - 1] and indicators.bb_width[index] > indicators.bb_width[index - 1]:
                return "終値が-2σを下回り、20日MA下向きかつBB幅が拡大しています"
    elif name == "MACDゴールデンクロス":
        if crossed_above(indicators.macd, indicators.macd_signal, index) and improving(indicators.macd_hist, index, 2):
            return "MACDがシグナルを上抜け、ヒストグラムが2日連続で改善しています"
    elif name == "MACDゼロライン上抜け":
        high20 = max_high(rows, index - 1, 20)
        if crossed_level_up(indicators.macd, index, 0) and signal and signal > 0 and high20 and close > high20:
            return "MACDがゼロラインを上抜け、シグナルも正で終値が20日高値を更新しています"
    elif name == "MACDヒストグラム加速":
        high5 = max_high(rows, index - 1, 5)
        if improving(indicators.macd_hist, index, 3) and high5 and close > high5:
            return "MACDヒストグラムが3日連続上昇し、終値が5日高値を更新しています"
    elif name == "MACD押し目再加速":
        if macd and macd > 0 and ma20 and close > ma20 and hist_reaccelerating(indicators.macd_hist, index):
            return "MACDが正で、ヒストグラムが一度低下後に再上昇し、終値が20日MAを上回っています"
    elif name == "MACD強気ダイバージェンス":
        if index > 0 and rows[index].close > (rows[index - 1].high if rows[index - 1].high is not None else rows[index - 1].close):
            if bullish_divergence(rows, indicators.macd, index - 1):
                return "価格が安値更新後、MACDは安値を切り上げ、当日終値が前日高値を上回っています"
    elif name == "MACD高位安定":
        if macd and signal and macd > 0 and signal > 0 and improving(indicators.macd, index, 5) and improving(indicators.macd_signal, index, 5):
            return "MACDとシグナルが正で、どちらも5日連続上昇しています"
    elif name == "MACDデッドクロス":
        if crossed_below(indicators.macd, indicators.macd_signal, index) and hist is not None and hist < 0:
            return "MACDがシグナルを下抜け、ヒストグラムがマイナスです"
    elif name == "MACDゼロライン下抜け":
        if crossed_level_down(indicators.macd, index, 0) and ma20 and close < ma20:
            return "MACDがゼロラインを下抜け、終値が20日MAを下回っています"
    elif name == "MACDヒストグラム減速":
        low5 = min_low(rows, index - 1, 5)
        if deteriorating(indicators.macd_hist, index, 3) and low5 and close < low5:
            return "MACDヒストグラムが3日連続低下し、終値が5日安値を更新しています"
    elif name == "MACD弱気ダイバージェンス":
        if index > 0 and rows[index].close < (rows[index - 1].low if rows[index - 1].low is not None else rows[index - 1].close):
            if bearish_divergence(rows, indicators.macd, index - 1):
                return "価格が高値更新後、MACDは高値を切り下げ、当日終値が前日安値を下回っています"
    elif name == "BBスクイーズ＋MACD上向き":
        if indicators.bb_width_rank_120[index] is not None and indicators.bb_width_rank_120[index] <= 20 and upper2 and close > upper2:
            if macd is not None and signal is not None and hist is not None and macd > signal and hist > 0:
                return "BB幅低位から+2σを上抜け、MACDがシグナルを上回りヒストグラムが正です"
    elif name == "BB上放れ＋MACDゼロ上":
        if upper2 and close > upper2 and macd and signal and macd > 0 and signal > 0 and index > 0 and ma20 and indicators.ma20[index - 1] and ma20 > indicators.ma20[index - 1]:
            return "終値が+2σを上抜け、MACDとシグナルが正で20日MAが上向きです"
    elif name == "BB中央線押し目＋MACD再加速":
        if ma20 and close > ma20 and min_distance_to_ma20(rows, indicators, index, 5) <= 0.02 and macd and macd > 0 and hist_reaccelerating(indicators.macd_hist, index):
            return "20日MA近辺から反発し、MACD正かつヒストグラムが再上昇しています"
    elif name == "BB下限反発＋MACD強気ダイバージェンス":
        if lower1 and close > lower1 and bullish_divergence(rows, indicators.macd, index):
            if any((rows[pos].low or rows[pos].close) < indicators.bb_lower_2[pos] for pos in range(max(0, index - 3), index + 1) if indicators.bb_lower_2[pos] is not None):
                return "-2σ割れ後に終値が-1σを回復し、MACDの強気ダイバージェンスが出ています"
    elif name == "BBバンドウォーク＋MACD高位継続":
        if count_closes_above(rows, indicators.bb_upper_1, index, 5) >= 3 and macd and macd > 0 and hist is not None and hist >= 0:
            return "終値が+1σ以上で3日以上推移し、MACD正かつヒストグラムが非負です"
    elif name == "BB収縮ブレイク＋MACD出来高確認":
        avg_volume = indicators.avg_volume20[index]
        volume = rows[index].volume
        if indicators.bb_width_rank_120[index] is not None and indicators.bb_width_rank_120[index] <= 25 and upper2 and close > upper2:
            if macd is not None and signal is not None and macd > signal and avg_volume and volume and volume > avg_volume * 1.5:
                return "BB幅低位から+2σを上抜け、MACDがシグナルを上回り出来高が急増しています"
    elif name == "BBフェイク下抜け＋MACD改善":
        if ma20 and close > ma20 and improving(indicators.macd_hist, index, 3):
            if any((rows[pos].low or rows[pos].close) < indicators.bb_lower_2[pos] for pos in range(max(0, index - 5), index + 1) if indicators.bb_lower_2[pos] is not None):
                return "-2σ割れ後に20日MAを回復し、MACDヒストグラムが3日連続改善しています"
    elif name == "BB高値更新＋MACD二段上げ":
        high20 = max_high(rows, index - 1, 20)
        if high20 and close > high20 and upper1 and close > upper1 and hist_breaks_recent_peak(indicators.macd_hist, index, 20):
            return "終値が20日高値と+1σを上回り、MACDヒストグラムが直近ピークを更新しています"
    elif name == "BB上限失速＋MACDデッドクロス":
        if upper1 and close < upper1 and crossed_below(indicators.macd, indicators.macd_signal, index) and hist is not None and hist < 0:
            return "終値が+1σを下回り、MACDデッドクロスとヒストグラム陰転が出ています"
    elif name == "BB中央線割れ＋MACD悪化":
        if ma20 and close < ma20 and deteriorating(indicators.macd_hist, index, 3):
            return "終値が20日MAを下回り、MACDヒストグラムが3日連続低下しています"
    elif name == "BB高ボラ反落＋MACD弱気化":
        if indicators.bb_width_rank_120_high[index] is not None and indicators.bb_width_rank_120_high[index] <= 20 and upper1 and close < upper1 and hist is not None and hist < 0:
            return "BB幅が高位で、終値が+1σを下回りMACDヒストグラムがマイナスです"
    elif name == "BB下抜け＋MACDゼロ下":
        if lower2 and close < lower2 and macd is not None and signal is not None and macd < 0 and signal < 0:
            return "終値が-2σを下回り、MACDとシグナルがともにマイナスです"
    elif name == "BB弱気ダイバージェンス確認":
        if index > 0 and rows[index].close < (rows[index - 1].low if rows[index - 1].low is not None else rows[index - 1].close):
            if bearish_divergence(rows, indicators.macd, index - 1):
                return "高値圏でMACD弱気ダイバージェンス後、当日終値が前日安値を下回っています"
    elif name == "高勝率フィルター付きBB＋MACD":
        if upper2 and close > upper2 and macd is not None and signal is not None and macd > signal and ma20 and ma60 and ma120 and ma20 > ma60 > ma120:
            return "終値が+2σを上抜け、MACDがシグナルを上回り20/60/120日MAが順行しています"
    elif name == "高騰落率フィルター付きBB＋MACD":
        avg_volume = indicators.avg_volume20[index]
        volume = rows[index].volume
        if indicators.bb_width_rank_120[index] is not None and indicators.bb_width_rank_120[index] <= 15 and upper2 and close > upper2:
            if hist_breaks_recent_peak(indicators.macd_hist, index, 20) and avg_volume and volume and volume > avg_volume * 1.5:
                return "BB幅が過去120日下位15%から+2σを上抜け、MACDヒストグラム最大更新と出来高急増が出ています"
    elif name == "誤シグナル回避ルール":
        if ma20 and close < ma20:
            return "終値が20日MAを下回っており、ブレイク失敗の回避条件に該当します"
        if hist is not None and hist < 0:
            return "MACDヒストグラムがマイナスで、ブレイク失敗の回避条件に該当します"
    elif name == "利伸ばし型トレーリング":
        if ma20 and close < ma20:
            return "終値が20日MAを下回り、利伸ばし型トレーリングの手仕舞い条件に該当します"
        if crossed_below(indicators.macd, indicators.macd_signal, index):
            return "MACDデッドクロスが発生し、利伸ばし型トレーリングの手仕舞い条件に該当します"
    return None


def is_supported_rule(name: str) -> bool:
    unsupported = {"ペア・スプレッド平均回帰の買い", "ペア・スプレッド割高売り"}
    return name not in unsupported


def average_close(rows: list[PriceRow], index: int, period: int) -> float | None:
    if index - period + 1 < 0:
        return None
    return mean(row.close for row in rows[index - period + 1 : index + 1])


def average_volume(rows: list[PriceRow], index: int, period: int) -> float | None:
    if index - period + 1 < 0:
        return None
    values = [row.volume for row in rows[index - period + 1 : index + 1] if row.volume is not None]
    return mean(values) if len(values) == period else None


def max_high(rows: list[PriceRow], index: int, period: int) -> float | None:
    if index - period + 1 < 0:
        return None
    values = [row.high if row.high is not None else row.close for row in rows[index - period + 1 : index + 1]]
    return max(values)


def min_low(rows: list[PriceRow], index: int, period: int) -> float | None:
    if index - period + 1 < 0:
        return None
    values = [row.low if row.low is not None else row.close for row in rows[index - period + 1 : index + 1]]
    return min(values)


def period_return(rows: list[PriceRow], index: int, period: int) -> float | None:
    if index - period < 0:
        return None
    prior = rows[index - period].close
    return (rows[index].close - prior) / prior * 100 if prior else None


def rsi(rows: list[PriceRow], index: int, period: int) -> float | None:
    if index - period < 0:
        return None
    gains = []
    losses = []
    for position in range(index - period + 1, index + 1):
        diff = rows[position].close - rows[position - 1].close
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bollinger(rows: list[PriceRow], index: int, period: int) -> tuple[float, float, float] | None:
    if index - period + 1 < 0:
        return None
    values = [row.close for row in rows[index - period + 1 : index + 1]]
    center = mean(values)
    deviation = pstdev(values)
    return center, center + deviation * 2, center - deviation * 2


def bollinger_width_percentile(rows: list[PriceRow], index: int, window: int) -> float | None:
    if index - window + 1 < 0:
        return None
    widths = []
    for position in range(index - window + 1, index + 1):
        band = bollinger(rows, position, 20)
        if band is None or band[0] == 0:
            continue
        widths.append((band[1] - band[2]) / band[0])
    if len(widths) < window - 19:
        return None
    current = widths[-1]
    return sum(1 for value in widths if value <= current) / len(widths) * 100


def atr(rows: list[PriceRow], index: int, period: int) -> float | None:
    if index - period + 1 <= 0:
        return None
    ranges = []
    for position in range(index - period + 1, index + 1):
        high = rows[position].high if rows[position].high is not None else rows[position].close
        low = rows[position].low if rows[position].low is not None else rows[position].close
        previous_close = rows[position - 1].close
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return mean(ranges)


def momentum_percentile(
    momentum_scores: dict[str, dict[int, float]],
    date: str,
    symbol_id: int,
) -> float | None:
    scores_by_symbol = momentum_scores.get(date, {})
    own_score = scores_by_symbol.get(symbol_id)
    if own_score is None:
        return None
    return percentile_rank(sorted(scores_by_symbol.values()), own_score)


def percentile_rank(sorted_scores: list[float], score: float | None) -> float | None:
    if score is None or not sorted_scores:
        return None
    below_or_equal = sum(1 for value in sorted_scores if value <= score)
    return below_or_equal / len(sorted_scores) * 100


def crossed_above(left: list[float | None], right: list[float | None], index: int) -> bool:
    if index <= 0:
        return False
    return (
        left[index - 1] is not None
        and right[index - 1] is not None
        and left[index] is not None
        and right[index] is not None
        and left[index - 1] <= right[index - 1]
        and left[index] > right[index]
    )


def crossed_below(left: list[float | None], right: list[float | None], index: int) -> bool:
    if index <= 0:
        return False
    return (
        left[index - 1] is not None
        and right[index - 1] is not None
        and left[index] is not None
        and right[index] is not None
        and left[index - 1] >= right[index - 1]
        and left[index] < right[index]
    )


def crossed_level_up(values: list[float | None], index: int, level: float) -> bool:
    if index <= 0 or values[index - 1] is None or values[index] is None:
        return False
    return values[index - 1] <= level < values[index]


def crossed_level_down(values: list[float | None], index: int, level: float) -> bool:
    if index <= 0 or values[index - 1] is None or values[index] is None:
        return False
    return values[index - 1] >= level > values[index]


def improving(values: list[float | None], index: int, days: int) -> bool:
    if index - days + 1 < 0:
        return False
    window = values[index - days + 1 : index + 1]
    if any(value is None for value in window):
        return False
    return all(window[position] > window[position - 1] for position in range(1, len(window)))


def deteriorating(values: list[float | None], index: int, days: int) -> bool:
    if index - days + 1 < 0:
        return False
    window = values[index - days + 1 : index + 1]
    if any(value is None for value in window):
        return False
    return all(window[position] < window[position - 1] for position in range(1, len(window)))


def hist_reaccelerating(values: list[float | None], index: int) -> bool:
    if index < 3:
        return False
    recent = values[index - 3 : index + 1]
    if any(value is None for value in recent):
        return False
    return recent[1] < recent[0] and recent[2] > recent[1] and recent[3] > recent[2]


def hist_breaks_recent_peak(values: list[float | None], index: int, period: int) -> bool:
    if index <= 0:
        return False
    current = values[index]
    if current is None:
        return False
    previous = [value for value in values[max(0, index - period) : index] if value is not None]
    return bool(previous) and current > max(previous)


def count_closes_above(rows: list[PriceRow], threshold: list[float | None], index: int, period: int) -> int:
    start = max(0, index - period + 1)
    return sum(
        1
        for position in range(start, index + 1)
        if threshold[position] is not None and rows[position].close > threshold[position]
    )


def min_distance_to_ma20(rows: list[PriceRow], indicators: IndicatorSeries, index: int, period: int) -> float:
    distances = []
    for position in range(max(0, index - period + 1), index + 1):
        ma20 = indicators.ma20[position]
        if ma20:
            distances.append(abs(rows[position].close - ma20) / ma20)
    return min(distances) if distances else 1.0


def bullish_divergence(rows: list[PriceRow], macd: list[float | None], index: int) -> bool:
    if index < 20 or macd[index] is None:
        return False
    recent_low_position = min(range(index - 9, index + 1), key=lambda position: rows[position].close)
    prior_low_position = min(range(index - 20, index - 9), key=lambda position: rows[position].close)
    return (
        rows[recent_low_position].close < rows[prior_low_position].close
        and macd[recent_low_position] is not None
        and macd[prior_low_position] is not None
        and macd[recent_low_position] > macd[prior_low_position]
    )


def bearish_divergence(rows: list[PriceRow], macd: list[float | None], index: int) -> bool:
    if index < 20 or macd[index] is None:
        return False
    recent_high_position = max(range(index - 9, index + 1), key=lambda position: rows[position].close)
    prior_high_position = max(range(index - 20, index - 9), key=lambda position: rows[position].close)
    return (
        rows[recent_high_position].close > rows[prior_high_position].close
        and macd[recent_high_position] is not None
        and macd[prior_high_position] is not None
        and macd[recent_high_position] < macd[prior_high_position]
    )
