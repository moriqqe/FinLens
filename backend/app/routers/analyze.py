from __future__ import annotations
import json
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import client_ip, get_current_user
from app.models.upload import Upload
from app.models.user import User
from app.schemas.upload import AnalyzeResponse
from app.services.audit import log_action
from app.services.crypto import decrypt, encrypt
from app.services.openai_client import analyze_transactions
from app.services.parsers.base import Transaction, deduplicate
from app.services.parsers.csv_ import parse_csv
from app.services.parsers.pdf_ import PdfEncryptedError, parse_pdf
from app.services.parsers.xls import parse_xls
from app.services.parsers.xlsx import parse_xlsx
from app.services.rate_limit import gpt_rate_limit, upload_rate_limit
from app.services.settings_store import get_setting_value

router = APIRouter()

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024

# Legacy Excel (BIFF / OLE compound document), not ZIP-based xlsx
OLE_XLS_MAGIC = b"\xd0\xcf\x11\xe0"


def transaction_to_dict(t: Transaction) -> dict:
    return {
        "date": str(t.date),
        "description": t.description,
        "category": t.category,
        "amount_uah": float(t.amount_uah),
        "orig_amount": float(t.orig_amount),
        "orig_currency": t.orig_currency,
        "is_expense": t.is_expense,
    }


def _sniff_pdf(content: bytes) -> bool:
    """Recognize PDF beyond only the first 4 bytes (BOM, leading junk, linearized files)."""
    if len(content) < 8:
        return False
    if content[:4] == b"%PDF":
        return True
    if content.startswith(b"\xef\xbb\xbf") and len(content) > 7 and content[3:7] == b"%PDF":
        return True
    return b"%PDF" in content[:8192]


def detect_format(filename: str, content: bytes) -> Optional[str]:
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf" and _sniff_pdf(content):
        return "pdf"
    if _sniff_pdf(content):
        return "pdf"
    # Legacy BIFF (.xls OLE). Some banks ship OOXML mislabeled as ".xls" (ZIP / PK).
    if ext == ".xls" and len(content) >= 4 and content[:4] == OLE_XLS_MAGIC:
        return "xls"
    if len(content) >= 2 and content[:2] == b"PK":
        if ext in (".xlsx", ".xlsm", ".xls"):
            return "xlsx"
    if ext == ".csv":
        return "csv"
    return None


async def parse_by_format(upload_file: UploadFile, fmt: str) -> List[Transaction]:
    await upload_file.seek(0)
    if fmt == "xlsx":
        return await parse_xlsx(upload_file)
    if fmt == "xls":
        return await parse_xls(upload_file)
    if fmt == "csv":
        return await parse_csv(upload_file)
    if fmt == "pdf":
        try:
            return await parse_pdf(upload_file)
        except PdfEncryptedError:
            raise HTTPException(status_code=400, detail="PDF is password protected or encrypted") from None
    raise HTTPException(status_code=400, detail="Unsupported file format")


async def resolve_openai_key(db: AsyncSession, user: User) -> Optional[str]:
    if user.use_admin_key:
        enc = await get_setting_value(db, "admin_key_encrypted")
        if not enc:
            return None
        return decrypt(enc)
    if user.api_key_encrypted:
        return decrypt(user.api_key_encrypted)
    return None


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_upload(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    files: list[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    await upload_rate_limit(str(user.id))

    merged: list[Transaction] = []
    names: list[str] = []
    formats: list[str] = []
    total_size = 0

    for f in files:
        content = await f.read()
        total_size += len(content)
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="File exceeds 20MB limit")
        fmt = detect_format(f.filename or "", content)
        if not fmt:
            raise HTTPException(status_code=400, detail=f"Unsupported or invalid file: {f.filename}")
        txs = await parse_by_format(f, fmt)
        merged.extend(txs)
        names.append(f.filename or "file")
        formats.append(fmt)

    if total_size > MAX_TOTAL_BYTES:
        raise HTTPException(status_code=400, detail="Total upload size exceeds 100MB")

    merged = deduplicate(merged)
    if not merged:
        raise HTTPException(status_code=400, detail="No transactions found in files")

    dates = [t.date for t in merged]
    date_from = min(dates)
    date_to = max(dates)
    total_expenses = Decimal(
        str(sum(abs(t.amount_uah) for t in merged if t.amount_uah < 0))
    )
    total_income = Decimal(str(sum(t.amount_uah for t in merged if t.amount_uah > 0)))
    ff = formats[0] if len(set(formats)) == 1 else "mixed"
    payload = json.dumps([transaction_to_dict(t) for t in merged])

    up = Upload(
        user_id=user.id,
        filename=", ".join(names),
        file_format=ff,
        transactions_data=encrypt(payload),
        tx_count=len(merged),
        date_from=date_from,
        date_to=date_to,
        total_expenses=total_expenses,
        total_income=total_income,
    )
    db.add(up)
    await log_action(
        db,
        "upload",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"filename": up.filename, "tx_count": len(merged)},
    )
    await db.commit()
    await db.refresh(up)

    key = await resolve_openai_key(db, user)
    if key:
        try:
            await gpt_rate_limit(str(user.id))
        except HTTPException:
            return AnalyzeResponse(upload_id=up.id, tx_count=len(merged))
        try:
            ai = await analyze_transactions(key, merged)
            up.ai_result = json.dumps(ai)
            await log_action(
                db,
                "analyze",
                user_id=user.id,
                ip=client_ip(request),
                user_agent=request.headers.get("user-agent"),
                details={"upload_id": str(up.id)},
            )
            await db.commit()
        except httpx.HTTPStatusError:
            await db.rollback()
        except Exception:
            await db.rollback()

    return AnalyzeResponse(upload_id=up.id, tx_count=len(merged))
