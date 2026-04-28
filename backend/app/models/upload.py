from __future__ import annotations
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Integer, Text, Date, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    transactions_data: Mapped[str] = mapped_column(Text, nullable=False)
    tx_count: Mapped[int] = mapped_column(Integer, nullable=False)
    date_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    total_expenses: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    total_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    ai_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
