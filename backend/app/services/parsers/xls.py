from __future__ import annotations

import xlrd
from fastapi import UploadFile
from xlrd import XL_CELL_DATE

from app.services.parsers.base import Transaction
from app.services.parsers.xlsx import parse_transaction_grid


def _xlrd_sheet_to_rows(sh, wb: xlrd.book.Book) -> list[list]:
    rows: list[list] = []
    for ri in range(sh.nrows):
        row: list = []
        for ci in range(sh.ncols):
            c = sh.cell(ri, ci)
            v = c.value
            if c.ctype == XL_CELL_DATE and isinstance(v, (float, int)):
                try:
                    from xlrd.xldate import xldate_as_datetime

                    dt = xldate_as_datetime(float(v), wb.datemode)
                    v = dt.date()
                except Exception:
                    pass
            row.append(v)
        rows.append(row)
    return rows


async def parse_xls(file: UploadFile) -> list[Transaction]:
    raw = await file.read()
    wb = xlrd.open_workbook(file_contents=raw)
    transactions: list[Transaction] = []
    for idx in range(wb.nsheets):
        sh = wb.sheet_by_index(idx)
        rows = _xlrd_sheet_to_rows(sh, wb)
        transactions.extend(parse_transaction_grid(rows))
    return transactions
