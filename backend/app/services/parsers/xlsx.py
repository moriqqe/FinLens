from __future__ import annotations
from datetime import date, datetime
from io import BytesIO

import openpyxl
from fastapi import UploadFile

from app.services.parsers.base import Transaction, is_self_transfer


def _cell_lower(row: tuple | list, j: int) -> str:
    if j < 0 or j >= len(row):
        return ""
    c = row[j]
    if c is None:
        return ""
    s = str(c).lower().strip()
    return " ".join(s.split())


def _parse_cell_date(raw) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if "\n" in s:
        s = s.split("\n", 1)[0].strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
        try:
            if len(fmt) > 10:
                return datetime.strptime(s[:19], fmt).date()
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _find_header(rows: list[list]) -> tuple[int, dict[str, int]]:
    """Locate header row and column indices; amount column no longer requires monobank-only substrings."""
    for i, row in enumerate(rows[:25]):
        if not row:
            continue
        cells = [_cell_lower(row, j) for j in range(len(row))]
        if not any(cells):
            continue

        has_date = any(
            "дата" in c
            or "date" in c
            or "дата і час" in c
            or "дата и время" in c
            or "date and time" in c
            for c in cells if c
        )
        if not has_date:
            continue

        cols: dict[str, int] = {}
        amount_candidates: list[tuple[int, int]] = []
        best_date_j = -1
        best_date_score = -1

        for j, c in enumerate(cells):
            if not c:
                continue
            ds = 0
            if "дата і час" in c or "дата и время" in c or "дата/час" in c:
                ds = 5
            elif c in ("дата", "date"):
                ds = 4
            elif "дата" in c and "оновл" not in c:
                ds = 3
            elif "date and time" in c:
                ds = 5
            elif "date" in c and len(c) < 22 and "update" not in c:
                ds = 2
            if ds > best_date_score:
                best_date_score = ds
                best_date_j = j

            if any(k in c for k in ("категор", "categ", "mcc", "тип операц", "тип операции")):
                cols["category"] = j
            if any(
                k in c
                for k in (
                    "опис",
                    "desc",
                    "назв",
                    "признач",
                    "details",
                    "merchant",
                    "отримувач",
                    "контрагент",
                    "платіж",
                    "призначення платежу",
                )
            ):
                cols["description"] = j
            if any(k in c for k in ("сума", "amount", "сумма", "sum")):
                score = 0
                if any(k in c for k in ("uah", "грн", "грив", "₴", "(uah)")):
                    score += 4
                if "card" in c and "amount" in c:
                    score += 5
                if "operation amount" in c and "card" not in c:
                    score += 1
                if "картк" in c or "карт " in c or "карта" in c:
                    score += 2
                if "транзакц" in c:
                    score += 2
                if "залишок" in c or "баланс" in c or "balance" in c:
                    score -= 3
                amount_candidates.append((score, j))

        if best_date_j >= 0:
            cols["date"] = best_date_j

        if amount_candidates:
            amount_candidates.sort(key=lambda x: (-x[0], x[1]))
            cols["amount_uah"] = amount_candidates[0][1]

        if "date" in cols and "amount_uah" in cols:
            for j, c in enumerate(cells):
                if not any(k in c for k in ("валют", "currency", "curr")):
                    continue
                # Skip "Card currency amount (UAH)" — pick "Operation currency", not amount columns
                if any(a in c for a in ("amount", "сума", "сумма", "sum")):
                    continue
                if "currency" not in cols:
                    cols["currency"] = j
            return i, cols

    return -1, {}


def parse_transaction_grid(rows: list[list]) -> list[Transaction]:
    """Shared row→transactions logic for XLSX (openpyxl) and legacy XLS (xlrd)."""
    header_row, cols = _find_header(rows)
    if header_row < 0:
        return []

    date_j = cols["date"]
    amt_j = cols["amount_uah"]
    desc_j = cols.get("description")
    cat_j = cols.get("category")
    cur_j = cols.get("currency")
    orig_amt_j = cols.get("amount_orig")
    orig_cur_j = cols.get("orig_currency")

    transactions: list[Transaction] = []
    for row in rows[header_row + 1 :]:
        if not row or all(c is None or c == "" for c in row):
            continue

        raw_date = row[date_j] if date_j < len(row) else None
        raw_amt = row[amt_j] if amt_j < len(row) else None

        tx_date = _parse_cell_date(raw_date)
        if tx_date is None:
            continue

        if raw_amt is None:
            continue
        try:
            amt = float(str(raw_amt).replace(" ", "").replace(",", ".").replace("\xa0", ""))
        except (ValueError, TypeError):
            continue

        desc = ""
        if desc_j is not None and desc_j < len(row):
            desc = str(row[desc_j] or "")
        cat = "Інше"
        if cat_j is not None and cat_j < len(row):
            cat = str(row[cat_j] or "Інше") or "Інше"
        currency = "UAH"
        if cur_j is not None and cur_j < len(row):
            currency = str(row[cur_j] or "UAH") or "UAH"
        orig_amt = amt
        if orig_amt_j is not None and orig_amt_j < len(row) and row[orig_amt_j] is not None:
            try:
                orig_amt = float(str(row[orig_amt_j]).replace(" ", "").replace(",", "."))
            except (ValueError, TypeError):
                orig_amt = amt
        orig_cur = currency
        if orig_cur_j is not None and orig_cur_j < len(row) and row[orig_cur_j]:
            orig_cur = str(row[orig_cur_j])

        if is_self_transfer(desc) or is_self_transfer(cat):
            continue

        transactions.append(
            Transaction(
                date=tx_date,
                description=desc,
                category=cat,
                amount_uah=amt,
                orig_amount=orig_amt,
                orig_currency=orig_cur,
                is_expense=amt < 0,
            )
        )
    return transactions


async def parse_xlsx(file: UploadFile) -> list[Transaction]:
    content = await file.read()
    wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    transactions: list[Transaction] = []

    for sheet in wb.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        transactions.extend(parse_transaction_grid(rows))

    wb.close()
    return transactions
