from __future__ import annotations
import csv
import io
from datetime import datetime
import chardet
from fastapi import UploadFile
from app.services.parsers.base import Transaction, is_self_transfer

DATE_FORMATS = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"]


def _detect_delimiter(text: str) -> str:
    best = ","
    best_count = 0
    for delim in [",", ";", "\t"]:
        try:
            reader = csv.reader(io.StringIO(text.split("\n")[0]), delimiter=delim)
            count = len(next(reader))
            if count > best_count:
                best_count = count
                best = delim
        except Exception:
            pass
    return best


def _parse_date(s: str) -> datetime | None:
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _find_col(headers: list[str], keywords: list[str]) -> int:
    for i, h in enumerate(headers):
        h_low = h.lower()
        if any(kw in h_low for kw in keywords):
            return i
    return -1


async def parse_csv(file: UploadFile) -> list[Transaction]:
    raw = await file.read()
    detected = chardet.detect(raw)
    encoding = detected.get("encoding") or "utf-8"
    text = raw.decode(encoding, errors="replace")

    delim = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = list(reader)
    if not rows:
        return []

    headers = rows[0]
    col_date = _find_col(headers, ["дата", "date"])
    col_cat = _find_col(headers, ["категор", "categ"])
    col_desc = _find_col(headers, ["опис", "desc", "назв"])
    col_amt = _find_col(headers, ["сума", "amount"])
    col_cur = _find_col(headers, ["валют"])

    if col_date < 0 or col_amt < 0:
        return []

    transactions = []
    for row in rows[1:]:
        if not row or len(row) <= max(col_date, col_amt):
            continue

        raw_date = row[col_date].strip()
        raw_amt = row[col_amt].strip().replace(" ", "").replace(",", ".")

        dt = _parse_date(raw_date)
        if not dt:
            continue
        try:
            amt = float(raw_amt)
        except ValueError:
            continue

        desc = row[col_desc].strip() if col_desc >= 0 and len(row) > col_desc else ""
        cat = row[col_cat].strip() if col_cat >= 0 and len(row) > col_cat else "Інше"
        orig_cur = row[col_cur].strip() if col_cur >= 0 and len(row) > col_cur else "UAH"

        if is_self_transfer(desc) or is_self_transfer(cat):
            continue

        transactions.append(Transaction(
            date=dt.date(),
            description=desc,
            category=cat or "Інше",
            amount_uah=amt,
            orig_amount=amt,
            orig_currency=orig_cur or "UAH",
            is_expense=amt < 0,
        ))

    return transactions
