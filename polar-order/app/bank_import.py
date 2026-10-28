"""Parse bank CSV exports and map memo → Chart of Accounts Nature."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any

# Nature must match Finance workbook Chart_of_Accounts exactly.
NATURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Rent", ("rent", "landlord", "租")),
    ("Rates (差餉)", ("rates", "差餉", "rating")),
    ("Management fee", ("management fee", "mgmt fee", "管理費")),
    ("Wages", ("wage", "salary", "payroll", "mpf", "人工", "薪")),
    ("Electricity", ("electric", "hke", "clp", "電費", "中電")),
    ("Water", ("water", "wsd", "水務", "水費")),
    ("Internet", ("hkbn", "internet", "broadband", "網上", "寬頻")),
    ("Marketing fee", ("marketing", "ads", "facebook", "meta ads", "google ads")),
    ("Wine cost", ("wine", "葡萄酒")),
    ("Drink / Alcohol", ("alcohol", "beer", "liquor", "spirit", "drink", "ypasta", "smokie")),
    ("Shisha stock", ("shisha", "hookah", "水煙", "tobacco")),
    ("Nuts / snacks", ("nuts", "snack", "果仁")),
    ("Other COGS", ("supplier", "invoice", "stock", "cogs", "采购", "進貨")),
    ("Claim", ("claim", "reimburse", "報銷", "墊支")),
    ("Repairs & maintenance", ("repair", "maintain", "grease", "維修", "保養")),
    ("Membership / BNI", ("bni", "membership", "會籍")),
    ("Partner cash in", ("partner cash in", "capital inject", "注資", "shareholder in")),
    ("Partner drawings", ("drawing", "partner draw", "股東提取", "dividend")),
    ("Partner capital", ("partner capital", "opening capital")),
    ("Sales", ("fps in", "payme", "stripe", "sales deposit", "卡機", "visa settle", "edc")),
    ("Deposits held", ("deposit", "按金", "tenancy deposit")),
    ("Miscellaneous", ()),  # fallback — matched last via default
)

ACCOUNT_CODES: dict[str, str] = {
    "HSBC SA": "1000",
    "HSBC CA": "1010",
    "Cash on hand": "1100",
    "Deposits held": "1200",
    "Partner capital": "3000",
    "Partner drawings": "3100",
    "Partner cash in": "3200",
    "Sales": "4000",
    "Drink / Alcohol": "5000",
    "Shisha stock": "5010",
    "Nuts / snacks": "5020",
    "Wine cost": "5030",
    "Other COGS": "5090",
    "Rent": "6000",
    "Management fee": "6010",
    "Rates (差餉)": "6020",
    "Wages": "6100",
    "Electricity": "6200",
    "Water": "6210",
    "Internet": "6220",
    "Marketing fee": "6300",
    "Claim": "6400",
    "Repairs & maintenance": "6500",
    "Miscellaneous": "6900",
    "Membership / BNI": "6910",
}

BANK_ENTRY_HEADERS: tuple[str, ...] = (
    "date",
    "memo",
    "chq_no",
    "hsbc_sa",
    "hsbc_ca",
    "nature",
    "account_code",
    "linked_sales_date",
    "notes",
)


def infer_nature(memo: str) -> str:
    text = (memo or "").lower()
    for nature, needles in NATURE_RULES:
        if nature == "Miscellaneous":
            continue
        if any(n in text for n in needles):
            return nature
    return "Miscellaneous"


def _parse_date(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    # Excel serial? skip
    return None


def _parse_amount(raw: str) -> float | None:
    s = (raw or "").strip().replace(",", "").replace("HKD", "").replace("$", "")
    if not s or s in { "-", "—" }:
        return None
    # (123.45) → negative
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (h or "").lower())


def _pick_col(headers: list[str], *candidates: str) -> int | None:
    norms = [_norm_header(h) for h in headers]
    for cand in candidates:
        c = _norm_header(cand)
        if c in norms:
            return norms.index(c)
    return None


def parse_bank_csv(
    text: str,
    *,
    account: str = "hsbc_ca",
) -> list[dict[str, Any]]:
    """Parse a flexible bank CSV into Bank_Entries rows.

    ``account``: ``hsbc_sa`` or ``hsbc_ca`` — which amount column to fill.
    Accepts columns like Date/Description/Amount or Date/Debit/Credit.
    """
    if account not in {"hsbc_sa", "hsbc_ca"}:
        raise ValueError("account must be hsbc_sa or hsbc_ca")

    sample = text.lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(sample[:4096], delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(sample), dialect=dialect)
    if not reader.fieldnames:
        return []

    headers = list(reader.fieldnames)
    date_i = _pick_col(headers, "date", "txn date", "transaction date", "value date", "交易日期")
    memo_i = _pick_col(
        headers,
        "memo",
        "description",
        "narrative",
        "details",
        "particulars",
        "交易詳情",
        "摘要",
    )
    amount_i = _pick_col(headers, "amount", "amt", "交易金額", "金額")
    debit_i = _pick_col(headers, "debit", "withdrawal", "money out", "支帳")
    credit_i = _pick_col(headers, "credit", "deposit", "money in", "入帳")
    chq_i = _pick_col(headers, "chq", "cheque", "chq no", "cheque no", "cheque number")

    if date_i is None or memo_i is None:
        raise ValueError(
            "CSV needs Date + Description columns "
            "(or 交易日期 + 交易詳情). Got: " + ", ".join(headers)
        )
    if amount_i is None and debit_i is None and credit_i is None:
        raise ValueError(
            "CSV needs Amount or Debit/Credit columns. Got: " + ", ".join(headers)
        )

    rows: list[dict[str, Any]] = []
    for raw in reader:
        vals = list(raw.values())
        d = _parse_date(vals[date_i] if date_i < len(vals) else "")
        memo = (vals[memo_i] if memo_i < len(vals) else "") or ""
        memo = str(memo).strip()
        if not d or not memo:
            continue

        amount = None
        if amount_i is not None:
            amount = _parse_amount(vals[amount_i] if amount_i < len(vals) else "")
        else:
            debit = _parse_amount(vals[debit_i] if debit_i is not None and debit_i < len(vals) else "")
            credit = _parse_amount(vals[credit_i] if credit_i is not None and credit_i < len(vals) else "")
            if credit:
                amount = abs(credit)
            elif debit:
                amount = -abs(debit)

        if amount is None or amount == 0:
            continue

        nature = infer_nature(memo)
        # Outflows for expense natures should be negative if CSV gave absolute debit already handled.
        entry = {
            "date": d,
            "memo": memo,
            "chq_no": (
                str(vals[chq_i]).strip()
                if chq_i is not None and chq_i < len(vals) and vals[chq_i]
                else ""
            ),
            "hsbc_sa": float(amount) if account == "hsbc_sa" else "",
            "hsbc_ca": float(amount) if account == "hsbc_ca" else "",
            "nature": nature,
            "account_code": ACCOUNT_CODES.get(nature, ""),
            "linked_sales_date": "",
            "notes": "imported",
            "fingerprint": f"{d}|{memo}|{amount:.2f}|{account}",
        }
        rows.append(entry)
    return rows


def rows_for_sheet(entries: list[dict[str, Any]]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for e in entries:
        out.append(
            [
                e.get("date", ""),
                e.get("memo", ""),
                e.get("chq_no", ""),
                e.get("hsbc_sa", "") if e.get("hsbc_sa", "") != "" else "",
                e.get("hsbc_ca", "") if e.get("hsbc_ca", "") != "" else "",
                e.get("nature", "Miscellaneous"),
                e.get("account_code", ""),
                e.get("linked_sales_date", ""),
                e.get("notes", "imported"),
            ]
        )
    return out
