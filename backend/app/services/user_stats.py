from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional

from app.models.upload import Upload
from app.services.parsers.base import deduplicate_transaction_dicts, parse_transaction_dict_date


def upload_overlaps_period(up: Upload, date_from: Optional[date], date_to: Optional[date]) -> bool:
    """Include uploads whose stored span may contain txs inside [date_from, date_to]."""
    if date_from is None and date_to is None:
        return True
    u_from = up.date_from
    u_to = up.date_to
    if u_from is None and u_to is None:
        return True
    if date_from is not None and u_to is not None and u_to < date_from:
        return False
    if date_to is not None and u_from is not None and u_from > date_to:
        return False
    return True


def tx_in_period(tx: dict, date_from: Optional[date], date_to: Optional[date]) -> bool:
    try:
        td = parse_transaction_dict_date(tx)
    except (ValueError, TypeError):
        return False
    if date_from is not None and td < date_from:
        return False
    if date_to is not None and td > date_to:
        return False
    return True


def totals_from_transactions(unique: list[dict]) -> tuple[Decimal, Decimal]:
    total_expenses = Decimal("0")
    total_income = Decimal("0")
    for tx in unique:
        try:
            amt = float(tx["amount_uah"])
        except (KeyError, TypeError, ValueError):
            continue
        if amt < 0:
            total_expenses += Decimal(str(abs(amt)))
        elif amt > 0:
            total_income += Decimal(str(amt))
    return total_expenses, total_income


def span_from_transactions(unique: list[dict]) -> tuple[Optional[date], Optional[date]]:
    dates: list[date] = []
    for tx in unique:
        try:
            dates.append(parse_transaction_dict_date(tx))
        except (ValueError, TypeError):
            continue
    if not dates:
        return None, None
    return min(dates), max(dates)
