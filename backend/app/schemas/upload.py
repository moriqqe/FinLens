from __future__ import annotations
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class UploadOut(BaseModel):
    id: uuid.UUID
    filename: str
    file_format: str
    tx_count: int
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    total_expenses: Optional[Decimal] = None
    total_income: Optional[Decimal] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalyzeResponse(BaseModel):
    upload_id: uuid.UUID
    tx_count: int


class UploadDetail(BaseModel):
    upload_id: uuid.UUID
    transactions: List[Dict[str, Any]]
    ai_result: Optional[Dict[str, Any]] = None


class UserStatsResponse(BaseModel):
    """Aggregate across all uploads; duplicates (same date + description + amount) counted once."""

    filter_date_from: Optional[date] = None
    filter_date_to: Optional[date] = None
    uploads_considered: int
    transactions_before_dedupe: int
    transactions_unique: int
    duplicates_removed: int
    total_expenses: Decimal
    total_income: Decimal
    actual_date_from: Optional[date] = None
    actual_date_to: Optional[date] = None
