from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class InvoiceOut(BaseModel):
    id: int
    source: str
    paperless_doc_id: int
    paperless_created: Optional[datetime.datetime] = None
    title: Optional[str] = None
    vendor: Optional[str] = None
    vendor_source: str
    amount: Optional[float] = None
    amount_source: str
    currency: str
    confidence: float
    needs_review: bool
    extracted_at: datetime.datetime
    updated_at: datetime.datetime
    debug_json: Optional[str] = None
    correspondent: Optional[str] = None
    document_type: Optional[str] = None
    ocr_text: Optional[str] = None
    ocr_snippet: Optional[str] = None

    model_config = {'from_attributes': True}


class InvoiceReviewListOut(BaseModel):
    total: int
    items: list[InvoiceOut]


class InvoiceUpdate(BaseModel):
    vendor: Optional[str] = None
    amount: Optional[float] = None
    needs_review: Optional[bool] = None
    reset_vendor: Optional[bool] = None
    reset_amount: Optional[bool] = None


class ManualCostCreate(BaseModel):
    date: Optional[datetime.date] = None
    vendor: str = Field(min_length=1)
    amount: float = Field(gt=0)
    currency: str = 'EUR'
    category: Optional[str] = None
    note: Optional[str] = None


class ManualCostUpdate(BaseModel):
    date: Optional[datetime.date] = None
    vendor: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = None
    category: Optional[str] = None
    note: Optional[str] = None


class ManualCostOut(BaseModel):
    id: int
    source: str
    date: datetime.date
    vendor: str
    amount: float
    currency: str
    category: Optional[str] = None
    note: Optional[str] = None
    is_archived: bool
    archived_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {'from_attributes': True}


class SyncErrorOut(BaseModel):
    count: int
    first_error: Optional[str] = None


class SyncResponse(BaseModel):
    started_at: datetime.datetime
    finished_at: datetime.datetime
    duration_ms: int
    checked_docs: int
    new_invoices: int
    updated_invoices: int
    skipped_invoices: int
    errors: SyncErrorOut


class KeyValueAmount(BaseModel):
    name: str
    amount: float


class CategoryAmount(BaseModel):
    category: str
    amount: float


class SummaryOut(BaseModel):
    total_amount: float
    paperless_total: float
    manual_total: float
    invoice_count: int
    manual_cost_count: int
    needs_review_count: int
    top_vendors: list[KeyValueAmount]
    costs_by_category: list[CategoryAmount]


class ConfigOut(BaseModel):
    paperless_base_url: str
    project_name: str
    project_tag_name: str
    pool_tag_name: str
    scheduler_enabled: bool
    scheduler_interval_minutes: int
    scheduler_run_on_startup: bool


class HealthOut(BaseModel):
    status: str
    paperless_ok: bool
    paperless_latency_ms: Optional[int] = None


class SyncRunOut(BaseModel):
    id: Optional[int] = None
    started_at: datetime.datetime
    finished_at: datetime.datetime
    duration_ms: int
    checked_docs: int
    new_invoices: int
    updated_invoices: int
    skipped_invoices: int
    errors: SyncErrorOut


class AllCostRow(BaseModel):
    date: Optional[str]
    source: str
    vendor: Optional[str]
    company: Optional[str] = None
    amount: Optional[float]
    amount_gross: Optional[float] = None
    currency: Optional[str]
    title: Optional[str]
    category: Optional[str]
    note: Optional[str]
    notes: Optional[str] = None
    project_name: Optional[str] = None
    project_tag: Optional[str] = None
    paperless_doc_id: Optional[int]
    paperless_url: Optional[str] = None
    confidence: Optional[float]
    needs_review: Optional[bool]


class ExtractionDebug(BaseModel):
    keyword: Optional[str] = None
    regex: Optional[str] = None
    context_snippet: Optional[str] = None
    vendor_source: Optional[str] = None
    candidates_checked: Optional[int] = None
    extra: Optional[Dict[str, Any]] = None
