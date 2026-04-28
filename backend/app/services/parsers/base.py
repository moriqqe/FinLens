from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime

SELF_TRANSFER_PATTERNS = [
    # Ukrainian
    "свою картку",
    "своєї картки",
    "на свою",
    "зі своєї",
    # English (bank exports)
    "own card",
    "to own",
    "from own",
    "between own",
    "transfer between accounts",
    "between accounts",
    "same holder",
    "internal transfer",
]


@dataclass
class Transaction:
    date: date
    description: str
    category: str
    amount_uah: float
    orig_amount: float
    orig_currency: str
    is_expense: bool

    def dedup_key(self) -> tuple:
        return (self.date, self.description, self.amount_uah)


def is_self_transfer(description: str) -> bool:
    desc = description.lower()
    return any(p in desc for p in SELF_TRANSFER_PATTERNS)


def deduplicate(transactions: list[Transaction]) -> list[Transaction]:
    seen: set[tuple] = set()
    result = []
    for t in transactions:
        key = t.dedup_key()
        if key not in seen:
            seen.add(key)
            result.append(t)
    return result


def parse_transaction_dict_date(tx: dict) -> date:
    raw = tx.get("date")
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    raise ValueError("invalid transaction date")


def transaction_dict_dedup_key(tx: dict) -> tuple:
    """Same tuple as Transaction.dedup_key() for encrypted JSON rows."""
    d = parse_transaction_dict_date(tx)
    desc = str(tx.get("description") or "").strip()
    amt = float(tx["amount_uah"])
    return (d, desc, amt)


def deduplicate_transaction_dicts(transactions: list[dict]) -> tuple[list[dict], int]:
    """Merge rows from several uploads; duplicates_removed counts overlaps between statements."""
    seen: set[tuple] = set()
    result: list[dict] = []
    skipped = 0
    for tx in transactions:
        try:
            key = transaction_dict_dedup_key(tx)
        except (KeyError, ValueError, TypeError):
            skipped += 1
            continue
        if key not in seen:
            seen.add(key)
            result.append(tx)
    duplicates_removed = len(transactions) - skipped - len(result)
    return result, duplicates_removed
