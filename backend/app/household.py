from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[2]
BANK_SAMPLE_PATH = ROOT_DIR / "銀行取引明細（サンプル）.csv"
DEBIT_SAMPLE_PATH = ROOT_DIR / "デビットカード明細（サンプル）.csv"


@dataclass(frozen=True)
class HouseholdImportRow:
    transacted_at: str
    amount: int
    direction: str
    category: str
    merchant: str
    description: str
    source_type: str
    source_key: str
    balance_after: int | None = None


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    for encoding in ("cp932", "utf-8-sig", "utf-8"):
        try:
            with path.open("r", encoding=encoding, newline="") as csv_file:
                return list(csv.DictReader(csv_file))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"CSV encoding is not supported: {path}")


def read_csv_bytes(content: bytes) -> list[dict[str, str]]:
    for encoding in ("cp932", "utf-8-sig", "utf-8"):
        try:
            text = content.decode(encoding)
            return list(csv.DictReader(io.StringIO(text)))
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV encoding is not supported")


def parse_sample_files() -> list[HouseholdImportRow]:
    rows: list[HouseholdImportRow] = []
    if DEBIT_SAMPLE_PATH.exists():
        rows.extend(parse_debit_rows(read_csv_rows(DEBIT_SAMPLE_PATH)))
    if BANK_SAMPLE_PATH.exists():
        rows.extend(parse_bank_rows(read_csv_rows(BANK_SAMPLE_PATH), skip_debit_withdrawals=True))
    return rows


def parse_uploaded_csv_files(files: Iterable[bytes]) -> list[HouseholdImportRow]:
    csv_rows = [read_csv_bytes(content) for content in files]
    has_debit = any(detect_csv_type(rows) == "debit" for rows in csv_rows)
    parsed: list[HouseholdImportRow] = []
    for rows in csv_rows:
        csv_type = detect_csv_type(rows)
        if csv_type == "bank":
            parsed.extend(parse_bank_rows(rows, skip_debit_withdrawals=has_debit))
        elif csv_type == "debit":
            parsed.extend(parse_debit_rows(rows))
        else:
            raise ValueError("Unknown household CSV format")
    return parsed


def detect_csv_type(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "unknown"
    fields = set(rows[0].keys())
    if {"取引日", "入出金(円)", "取引後残高(円)", "入出金内容"}.issubset(fields):
        return "bank"
    if {"ご利用日", "ご利用先", "ご利用金額（円）", "承認番号"}.issubset(fields):
        return "debit"
    return "unknown"


def parse_bank_rows(rows: Iterable[dict[str, str]], skip_debit_withdrawals: bool = False) -> list[HouseholdImportRow]:
    parsed: list[HouseholdImportRow] = []
    for index, row in enumerate(rows):
        raw_amount = parse_int(row.get("入出金(円)") or "0")
        description = clean_text(row.get("入出金内容") or "")
        if skip_debit_withdrawals and description.startswith("VISAデビット"):
            continue
        amount = abs(raw_amount)
        if amount == 0:
            continue
        direction = "income" if raw_amount > 0 else "expense"
        merchant = normalize_merchant(description)
        category = infer_category(merchant, description, direction)
        date = parse_yyyymmdd(row.get("取引日") or "")
        source_key = f"{date}:{raw_amount}:{row.get('取引後残高(円)', '')}:{description}:{index}"
        parsed.append(
            HouseholdImportRow(
                transacted_at=date,
                amount=amount,
                direction=direction,
                category=category,
                merchant=merchant,
                description=description,
                source_type="bank",
                source_key=source_key,
                balance_after=parse_optional_int(row.get("取引後残高(円)") or ""),
            )
        )
    return parsed


def parse_debit_rows(rows: Iterable[dict[str, str]]) -> list[HouseholdImportRow]:
    parsed: list[HouseholdImportRow] = []
    for index, row in enumerate(rows):
        amount = parse_int(row.get("口座引落分（円）") or row.get("ご利用金額（円）") or "0")
        if amount == 0:
            continue
        merchant = normalize_merchant(row.get("ご利用先") or "")
        date = parse_yyyymmdd(row.get("ご利用日") or "")
        approval = row.get("承認番号") or ""
        reference = row.get("照会番号") or ""
        description = clean_text(" / ".join(value for value in [merchant, row.get("使用地域") or "", reference] if value))
        parsed.append(
            HouseholdImportRow(
                transacted_at=date,
                amount=abs(amount),
                direction="expense",
                category=infer_category(merchant, description, "expense"),
                merchant=merchant,
                description=description,
                source_type="debit",
                source_key=f"{date}:{approval}:{reference}:{amount}:{index}",
            )
        )
    return parsed


def insert_import_rows(db, rows: Iterable[HouseholdImportRow]) -> dict[str, int]:
    imported = 0
    skipped = 0
    for row in rows:
        cursor = db.execute(
            """
            INSERT OR IGNORE INTO household_transactions (
              transacted_at, amount, direction, category, merchant, description,
              source_type, source_key, balance_after
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.transacted_at,
                row.amount,
                row.direction,
                row.category,
                row.merchant,
                row.description,
                row.source_type,
                row.source_key,
                row.balance_after,
            ),
        )
        if cursor.rowcount:
            imported += 1
        else:
            skipped += 1
    return {"imported": imported, "skipped": skipped}


def exclude_matching_bank_debit_withdrawals(db, rows: Iterable[HouseholdImportRow]) -> int:
    excluded = 0
    for row in rows:
        if row.source_type != "debit":
            continue
        approval_match = re.search(r":(\d{4,6}):", row.source_key)
        if not approval_match:
            continue
        approval = approval_match.group(1).lstrip("0")
        if not approval:
            continue
        cursor = db.execute(
            """
            UPDATE household_transactions
            SET excluded = 1, updated_at = CURRENT_TIMESTAMP
            WHERE source_type = 'bank'
              AND excluded = 0
              AND transacted_at BETWEEN date(?, '-7 day') AND date(?, '+7 day')
              AND amount = ?
              AND description LIKE ?
            """,
            (row.transacted_at, row.transacted_at, row.amount, f"%A{approval}%"),
        )
        excluded += cursor.rowcount
    return excluded


def month_key(date_text: str) -> str:
    return date_text[:7]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_yyyymmdd(value: str) -> str:
    value = value.strip().replace("/", "").replace("-", "")
    if not re.fullmatch(r"\d{8}", value):
        raise ValueError(f"Invalid date: {value}")
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def parse_int(value: str) -> int:
    normalized = value.strip().replace(",", "").replace('"', "")
    return int(normalized or "0")


def parse_optional_int(value: str) -> int | None:
    stripped = value.strip()
    return parse_int(stripped) if stripped else None


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalize_merchant(value: str) -> str:
    text = clean_text(value).upper()
    replacements = {
        "ＡＭＡＺＯＮ．ＣＯ．ＪＰ": "AMAZON.CO.JP",
        "ＳＴＥＡＭ": "STEAM",
        "ﾗｸﾃﾝﾍﾟｲ": "楽天ペイ",
        "ｄアニメストア（月額）": "dアニメストア",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def infer_category(merchant: str, description: str, direction: str) -> str:
    if direction == "income":
        return "収入"
    text = f"{merchant} {description}".upper()
    rules = [
        ("食費", r"スーパー|イオン|カスミ|コンビニ|セブン|ローソン|ファミリ|楽天ペイ"),
        ("日用品", r"AMAZON|ドラッグ|薬局|ホームセンター"),
        ("娯楽", r"STEAM|ゲーム|映画|カラオケ"),
        ("サブスク", r"アニメ|NETFLIX|SPOTIFY|YOUTUBE|月額"),
        ("交通", r"SUICA|PASMO|駅|タクシー|バス"),
        ("通信", r"DOCOMO|AU|SOFTBANK|通信|携帯"),
        ("住居", r"家賃|電気|ガス|水道"),
        ("投資・貯蓄", r"証券|NISA|積立|振替"),
        ("手数料", r"手数料"),
    ]
    for category, pattern in rules:
        if re.search(pattern, text):
            return category
    return "その他"
