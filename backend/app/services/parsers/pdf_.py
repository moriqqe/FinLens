from __future__ import annotations
import io
import re
from datetime import date, datetime

import pdfplumber
from fastapi import UploadFile

from app.services.parsers.base import Transaction, is_self_transfer


DATE_KEYWORDS = (
    "дата",
    "date",
    "time",
    "posted",
    "posting",
    "datetime",
    "transaction date",
    "post date",
    "value date",
)

AMOUNT_KEYWORDS = (
    "сума",
    "amount",
    "sum",
    "debit",
    "credit",
    "uah",
    "eur",
    "usd",
    "gbp",
    "грн",
)

DESC_KEYWORDS = (
    "опис",
    "desc",
    "description",
    "details",
    "merchant",
    "payee",
    "counterparty",
    "narrative",
    "purpose",
    "reference",
)

DATE_RE = re.compile(
    r"\d{2}[./-]\d{2}[./-]\d{4}|"
    r"\d{4}[./-]\d{2}[./-]\d{2}|"
    r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
)

AMT_RE_EU = re.compile(r"(-?\d[\d\s]*[.,]\d{2})\s*(UAH|EUR|USD|GBP|₴|\$|£)?", re.I)
AMT_RE_US = re.compile(r"(-?\d{1,3}(?:,\d{3})*\.\d{2})\s*(UAH|EUR|USD|GBP|\$)?", re.I)


class PdfEncryptedError(Exception):
    pass


def _parse_date(s: str) -> date | None:
    s = str(s).strip()
    if "\n" in s:
        s = s.split("\n", 1)[0].strip()
    if not s:
        return None
    fmts = (
        "%d.%m.%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%b %d %Y",
    )
    for fmt in fmts:
        for chunk in (s, s[:19], s[:16], s[:10]):
            try:
                return datetime.strptime(chunk, fmt).date()
            except ValueError:
                continue
    m = re.match(r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", s)
    if m:
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(m.group(1), fmt).date()
            except ValueError:
                continue
    return None


def _parse_amount_from_cell(text: str) -> float | None:
    if not text or not str(text).strip():
        return None
    compact = re.sub(r"[\s\xa0]", "", str(text))

    m = AMT_RE_US.search(compact)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    m = AMT_RE_EU.search(compact)
    if not m:
        m = re.search(r"(-?\d+[.,]\d{2})", compact)
    if not m:
        return None
    raw = m.group(1).replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            raw = parts[0].replace(".", "") + "." + parts[1]
        else:
            raw = raw.replace(",", "")
    else:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _cell_lower(cell) -> str:
    s = str(cell or "").lower().strip()
    return " ".join(s.split())


def _table_has_headers(header_cells: list[str]) -> bool:
    joined = " ".join(header_cells)
    has_date = any(any(k in h for k in DATE_KEYWORDS) for h in header_cells if h)
    has_amt = any(any(k in h for k in AMOUNT_KEYWORDS) for h in header_cells if h)
    if not has_date:
        has_date = any(x in joined for x in ("transaction date", "post date", "value date"))
    if not has_amt:
        has_amt = any(x in joined for x in ("amount", "debit", "credit", "sum"))
    return has_date and has_amt


def _pick_columns(header: list[str]) -> tuple[int, int, int]:
    cells = [_cell_lower(c) for c in header]
    best_amt = (-999, -1)
    best_date = (-1, -1)

    for i, h in enumerate(cells):
        ds = 0
        if any(x in h for x in ("дата і час", "transaction date", "post date", "value date")):
            ds = 5
        elif "date and time" in h:
            ds = 5
        elif h in ("дата", "date") or h.startswith("date "):
            ds = 4
        elif "дата" in h:
            ds = 3
        elif "date" in h and len(h) < 28:
            ds = 3
        elif "posted" in h or "posting" in h:
            ds = 3
        if ds > best_date[0]:
            best_date = (ds, i)

        score = 0
        if any(k in h for k in ("uah", "грн", "amount in", "in uah", "(uah)")):
            score += 4
        if "card" in h and "amount" in h:
            score += 5
        if any(k in h for k in ("сума", "amount", "sum")) and "balance" not in h:
            score += 3
        if "operation amount" in h and "card" not in h:
            score += 1
        if any(k in h for k in ("debit", "credit")):
            score += 2
        if "balance" in h or "залишок" in h:
            score -= 4
        if score > best_amt[0]:
            best_amt = (score, i)

    col_date = best_date[1] if best_date[1] >= 0 else 0
    col_amt = best_amt[1] if best_amt[1] >= 0 else min(2, max(0, len(cells) - 1))

    col_desc = 1
    best_ds = -1
    for i, h in enumerate(cells):
        sc = 0
        for k in DESC_KEYWORDS:
            if k in h:
                sc = max(sc, len(k))
        if sc > best_ds:
            best_ds = sc
            col_desc = i

    return col_date, col_desc, col_amt


async def parse_pdf(file: UploadFile) -> list[Transaction]:
    raw = await file.read()
    transactions: list[Transaction] = []
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                page_txs: list[Transaction] = []
                tables = page.extract_tables() or []
                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    header_row_idx = -1
                    header: list[str] = []
                    for hi in range(min(4, len(table))):
                        row = table[hi]
                        if not row:
                            continue
                        cand = [_cell_lower(c) for c in row]
                        if _table_has_headers(cand):
                            header_row_idx = hi
                            header = cand
                            break

                    if header_row_idx < 0:
                        continue

                    col_date, col_desc, col_amt = _pick_columns(header)

                    for row in table[header_row_idx + 1 :]:
                        if not row:
                            continue
                        max_idx = max(col_date, col_desc, col_amt, len(row) - 1)
                        row = list(row)
                        while len(row) <= max_idx:
                            row.append(None)

                        ds = str(row[col_date] or "").strip()
                        desc = str(row[col_desc] if col_desc < len(row) else "") or ""
                        amt_cell = str(row[col_amt] if col_amt < len(row) else "") or ""

                        tx_date = _parse_date(ds)
                        if not tx_date:
                            dm = DATE_RE.search(ds)
                            if dm:
                                tx_date = _parse_date(dm.group(0))
                        amt = _parse_amount_from_cell(amt_cell)
                        if not tx_date or amt is None:
                            continue
                        if is_self_transfer(desc):
                            continue
                        page_txs.append(
                            Transaction(
                                date=tx_date,
                                description=desc,
                                category="Інше",
                                amount_uah=amt,
                                orig_amount=amt,
                                orig_currency="UAH",
                                is_expense=amt < 0,
                            )
                        )

                if not page_txs:
                    text = page.extract_text() or ""
                    for line in text.splitlines():
                        compact = re.sub(r"\s+", "", line).replace("\xa0", "")
                        dm = DATE_RE.search(compact)
                        am = AMT_RE_EU.search(compact) or AMT_RE_US.search(compact)
                        if not dm or not am:
                            continue
                        tx_date = _parse_date(dm.group(0))
                        amt = _parse_amount_from_cell(compact)
                        if not tx_date or amt is None:
                            continue
                        desc_mid = compact[dm.end() : am.start()]
                        desc = desc_mid.strip() or "—"
                        if is_self_transfer(desc):
                            continue
                        page_txs.append(
                            Transaction(
                                date=tx_date,
                                description=desc,
                                category="Інше",
                                amount_uah=amt,
                                orig_amount=amt,
                                orig_currency="UAH",
                                is_expense=amt < 0,
                            )
                        )
                transactions.extend(page_txs)
    except Exception as exc:
        msg = str(exc).lower()
        if "password" in msg or "encrypt" in msg:
            raise PdfEncryptedError() from exc
        raise
    return transactions
