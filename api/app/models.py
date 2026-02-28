from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Invoice(Base):
    __tablename__ = 'invoices'
    __table_args__ = (UniqueConstraint('paperless_doc_id', name='uq_invoices_paperless_doc_id'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default='paperless', nullable=False)
    paperless_doc_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    paperless_created: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vendor_auto: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vendor_source: Mapped[str] = mapped_column(String(16), default='auto', nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    amount_auto: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    amount_source: Mapped[str] = mapped_column(String(16), default='auto', nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default='EUR', nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    debug_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    correspondent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    document_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ManualCost(Base):
    __tablename__ = 'manual_costs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default='manual', nullable=False)
    date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default='EUR', nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SyncRun(Base):
    __tablename__ = 'sync_runs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_docs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_invoices: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_invoices: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_invoices: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
