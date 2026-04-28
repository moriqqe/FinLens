from __future__ import annotations
import json
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import client_ip, get_current_user
from app.models.upload import Upload
from app.models.user import User
from app.schemas.auth import ApiKeyRequest
from app.schemas.upload import UploadDetail, UploadOut, UserStatsResponse
from app.services.audit import log_action
from app.services.crypto import decrypt, encrypt
from app.services.parsers.base import deduplicate_transaction_dicts
from app.services.user_stats import (
    span_from_transactions,
    totals_from_transactions,
    tx_in_period,
    upload_overlaps_period,
)

router = APIRouter()


@router.get("/stats", response_model=UserStatsResponse)
async def user_aggregate_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    date_from: Optional[date] = Query(None, description="Inclusive start (UTC date from stored rows)"),
    date_to: Optional[date] = Query(None, description="Inclusive end"),
):
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be <= date_to")

    result = await db.execute(
        select(Upload).where(Upload.user_id == user.id).order_by(Upload.created_at.asc())
    )
    uploads = list(result.scalars().all())

    merged_raw: list[dict] = []
    uploads_considered = 0

    for up in uploads:
        if not upload_overlaps_period(up, date_from, date_to):
            continue
        try:
            txs = json.loads(decrypt(up.transactions_data))
        except Exception:
            continue
        if not isinstance(txs, list):
            continue
        uploads_considered += 1
        for tx in txs:
            if not isinstance(tx, dict):
                continue
            if not tx_in_period(tx, date_from, date_to):
                continue
            merged_raw.append(tx)

    unique_txs, duplicates_removed = deduplicate_transaction_dicts(merged_raw)
    total_expenses, total_income = totals_from_transactions(unique_txs)
    actual_from, actual_to = span_from_transactions(unique_txs)

    return UserStatsResponse(
        filter_date_from=date_from,
        filter_date_to=date_to,
        uploads_considered=uploads_considered,
        transactions_before_dedupe=len(merged_raw),
        transactions_unique=len(unique_txs),
        duplicates_removed=duplicates_removed,
        total_expenses=total_expenses,
        total_income=total_income,
        actual_date_from=actual_from,
        actual_date_to=actual_to,
    )


@router.get("/uploads", response_model=list[UploadOut])
async def list_uploads(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Upload).where(Upload.user_id == user.id).order_by(Upload.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/uploads/{upload_id}", response_model=UploadDetail)
async def get_upload(
    upload_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(select(Upload).where(Upload.id == upload_id, Upload.user_id == user.id))
    up = row.scalar_one_or_none()
    if not up:
        raise HTTPException(status_code=404, detail="Upload not found")
    try:
        txs = json.loads(decrypt(up.transactions_data))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not decrypt data") from exc
    ai = None
    if up.ai_result:
        try:
            ai = json.loads(up.ai_result)
        except json.JSONDecodeError:
            ai = None
    return UploadDetail(upload_id=up.id, transactions=txs, ai_result=ai)


@router.delete("/uploads/{upload_id}", status_code=204)
async def delete_upload(
    upload_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(select(Upload).where(Upload.id == upload_id, Upload.user_id == user.id))
    up = row.scalar_one_or_none()
    if not up:
        raise HTTPException(status_code=404, detail="Upload not found")
    await db.execute(delete(Upload).where(Upload.id == upload_id, Upload.user_id == user.id))
    await log_action(
        db,
        "upload_delete",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"upload_id": str(upload_id)},
    )
    await db.commit()


@router.post("/api-key")
async def set_user_api_key(
    body: ApiKeyRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.api_key_encrypted = encrypt(body.api_key.strip())
    user.use_admin_key = False
    await log_action(
        db,
        "api_key_set",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return {"ok": True}


@router.delete("/api-key")
async def delete_user_api_key(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.api_key_encrypted = None
    await log_action(
        db,
        "api_key_delete",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return {"ok": True}
