from __future__ import annotations

import csv
import io
import json
import re
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .date_ranges import apply_date_filter_to_date, apply_date_filter_to_datetime, resolve_date_range
from .database import Base, SessionLocal, engine, ensure_schema_compatibility, get_db
from .models import Invoice, ManualCost, SyncRun
from .paperless import PaperlessClient
from .scheduler import SyncScheduler
from .schemas import ConfigOut, HealthOut, InvoiceOut, InvoiceReviewListOut, InvoiceUpdate, ManualCostCreate, ManualCostOut, ManualCostUpdate, SummaryOut, SyncResponse, SyncRunOut
from .settings import Settings, get_settings
from .sync_service import sync_invoices, sync_run_to_out

scheduler: SyncScheduler | None = None


def _invoice_to_out(invoice: Invoice) -> InvoiceOut:
    snippet = None
    if invoice.debug_json:
        try:
            debug = json.loads(invoice.debug_json)
            snippet = debug.get('context_snippet')
        except json.JSONDecodeError:
            snippet = None
    return InvoiceOut(
        id=invoice.id,
        source=invoice.source,
        paperless_doc_id=invoice.paperless_doc_id,
        paperless_created=invoice.paperless_created,
        title=invoice.title,
        vendor=invoice.vendor,
        vendor_source=invoice.vendor_source,
        amount=float(invoice.amount) if invoice.amount is not None else None,
        amount_source=invoice.amount_source,
        currency=invoice.currency,
        confidence=invoice.confidence,
        needs_review=invoice.needs_review,
        extracted_at=invoice.extracted_at,
        updated_at=invoice.updated_at,
        debug_json=invoice.debug_json,
        correspondent=invoice.correspondent,
        document_type=invoice.document_type,
        ocr_text=invoice.ocr_text,
        ocr_snippet=snippet,
    )


def _manual_to_out(item: ManualCost) -> ManualCostOut:
    return ManualCostOut(
        id=item.id,
        source=item.source,
        date=item.date,
        vendor=item.vendor,
        amount=float(item.amount),
        currency=item.currency,
        category=item.category,
        note=item.note,
        is_archived=item.is_archived,
        archived_at=item.archived_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _run_sync_job() -> None:
    db = SessionLocal()
    try:
        await sync_invoices(db, get_settings())
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility(engine)
    settings = get_settings()
    scheduler = SyncScheduler(settings, _run_sync_job)
    await scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()


app = FastAPI(title='pool-cost-tracker API', lifespan=lifespan)


def _resolve_requested_date_range(
    range_key: str,
    from_value: Optional[str],
    to_value: Optional[str],
):
    try:
        normalized_range_key = range_key if isinstance(range_key, str) else 'month'
        normalized_from_value = from_value if isinstance(from_value, str) else None
        normalized_to_value = to_value if isinstance(to_value, str) else None
        return resolve_date_range(
            range_key=normalized_range_key,
            from_value=normalized_from_value,
            to_value=normalized_to_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _get_last_sync_run_record(db: Session) -> Optional[SyncRun]:
    return db.scalar(select(SyncRun).order_by(SyncRun.finished_at.desc(), SyncRun.id.desc()).limit(1))


def _normalize_archived_filter(value: str = 'active') -> str:
    normalized = value.strip().lower() if isinstance(value, str) else 'active'
    if normalized not in {'active', 'archived', 'all'}:
        raise HTTPException(status_code=422, detail="Ungültiger archived-Wert. Erlaubt: active, archived, all.")
    return normalized


def _normalize_source_filter(value: str = 'all') -> str:
    normalized = value.strip().lower() if isinstance(value, str) else 'all'
    if normalized not in {'paperless', 'manual', 'all'}:
        raise HTTPException(status_code=422, detail="Ungültiger source-Wert. Erlaubt: paperless, manual, all.")
    return normalized


def _normalize_sort(value: str = 'date_desc') -> str:
    normalized = value.strip().lower() if isinstance(value, str) else 'date_desc'
    if normalized not in {'date_desc', 'date_asc', 'amount_desc', 'amount_asc'}:
        raise HTTPException(status_code=422, detail="Ungültiger sort-Wert. Erlaubt: date_desc, date_asc, amount_desc, amount_asc.")
    return normalized


def _normalize_review_sort(value: str = 'amount_desc') -> str:
    normalized = value.strip().lower() if isinstance(value, str) else 'amount_desc'
    if normalized not in {'amount_desc', 'date_desc'}:
        raise HTTPException(status_code=422, detail="Ungültiger review-sort-Wert. Erlaubt: amount_desc, date_desc.")
    return normalized


def _normalize_export_needs_review(value: str = 'all') -> Optional[bool]:
    normalized = value.strip().lower() if isinstance(value, str) else 'all'
    if normalized == 'all':
        return None
    if normalized == 'true':
        return True
    if normalized == 'false':
        return False
    raise HTTPException(status_code=422, detail="Ungültiger needs_review-Wert. Erlaubt: true, false, all.")


def _build_invoice_stmt(
    date_range,
    *,
    search: Optional[str] = None,
    needs_review: Optional[bool] = None,
    sort: str = 'date_desc',
):
    stmt = select(Invoice)
    stmt = apply_date_filter_to_datetime(stmt, Invoice.paperless_created, date_range)
    if needs_review is not None:
        stmt = stmt.where(Invoice.needs_review == needs_review)
    search_term = search.strip() if isinstance(search, str) else ''
    if search_term:
        like = f'%{search_term}%'
        stmt = stmt.where(or_(Invoice.vendor.ilike(like), Invoice.title.ilike(like)))

    normalized_sort = _normalize_sort(sort)
    if normalized_sort == 'amount_desc':
        stmt = stmt.order_by(Invoice.amount.desc().nullslast(), Invoice.id.desc())
    elif normalized_sort == 'amount_asc':
        stmt = stmt.order_by(Invoice.amount.asc().nullsfirst(), Invoice.id.desc())
    elif normalized_sort == 'date_asc':
        stmt = stmt.order_by(Invoice.paperless_created.asc().nullsfirst(), Invoice.id.desc())
    else:
        stmt = stmt.order_by(Invoice.paperless_created.desc().nullslast(), Invoice.id.desc())
    return stmt


def _build_manual_stmt(
    date_range,
    *,
    archived: str = 'active',
    search: Optional[str] = None,
    sort: str = 'date_desc',
):
    stmt = select(ManualCost)
    stmt = apply_date_filter_to_date(stmt, ManualCost.date, date_range)

    archived_mode = _normalize_archived_filter(archived)
    if archived_mode == 'active':
        stmt = stmt.where(ManualCost.is_archived.is_(False))
    elif archived_mode == 'archived':
        stmt = stmt.where(ManualCost.is_archived.is_(True))

    search_term = search.strip() if isinstance(search, str) else ''
    if search_term:
        like = f'%{search_term}%'
        stmt = stmt.where(ManualCost.vendor.ilike(like))

    normalized_sort = _normalize_sort(sort)
    if normalized_sort == 'amount_desc':
        stmt = stmt.order_by(ManualCost.amount.desc(), ManualCost.id.desc())
    elif normalized_sort == 'amount_asc':
        stmt = stmt.order_by(ManualCost.amount.asc(), ManualCost.id.desc())
    elif normalized_sort == 'date_asc':
        stmt = stmt.order_by(ManualCost.date.asc(), ManualCost.id.desc())
    else:
        stmt = stmt.order_by(ManualCost.date.desc(), ManualCost.id.desc())
    return stmt


def _paperless_document_url(settings: Settings, doc_id: Optional[int]) -> str:
    if doc_id is None:
        return ''
    base_url = (settings.PAPERLESS_BASE_URL or '').strip()
    if not base_url:
        return ''
    return f"{base_url.rstrip('/')}/documents/{doc_id}/details/"


def _project_category_presets(settings: Settings) -> list[str]:
    if not settings.PROJECT_CATEGORY_PRESETS:
        return []
    return [part.strip() for part in settings.PROJECT_CATEGORY_PRESETS.split(',') if part.strip()]


def _export_filename(settings: Settings) -> str:
    today = datetime.now(ZoneInfo(settings.PROJECT_TIMEZONE)).date().isoformat()
    slug = re.sub(r'[^a-z0-9]+', '-', settings.PROJECT_NAME.lower()).strip('-') or 'project'
    return f'{slug}_{today}_export.csv'


@app.get('/health', response_model=HealthOut)
async def health():
    settings = get_settings()
    paperless_ok = False
    paperless_latency_ms = None
    try:
        paperless_latency_ms = await PaperlessClient(settings).probe()
        paperless_ok = True
    except Exception:  # pragma: no cover - health endpoint should degrade gracefully
        paperless_ok = False
    return {'status': 'ok', 'paperless_ok': paperless_ok, 'paperless_latency_ms': paperless_latency_ms}


@app.get('/config', response_model=ConfigOut)
def get_config():
    settings = get_settings()
    return ConfigOut(
        paperless_base_url=settings.PAPERLESS_BASE_URL,
        project_name=settings.PROJECT_NAME,
        project_tag_name=settings.PROJECT_TAG_NAME,
        pool_tag_name=settings.POOL_TAG_NAME,
        default_currency=settings.DEFAULT_CURRENCY,
        category_presets=_project_category_presets(settings),
        timezone=settings.PROJECT_TIMEZONE,
        scheduler_enabled=settings.SCHEDULER_ENABLED,
        scheduler_interval_minutes=settings.SCHEDULER_INTERVAL_MINUTES,
        scheduler_run_on_startup=settings.SCHEDULER_RUN_ON_STARTUP,
    )


@app.post('/sync', response_model=SyncResponse)
async def run_sync(db: Session = Depends(get_db)):
    settings = get_settings()
    if not (settings.PAPERLESS_BASE_URL or '').strip():
        raise HTTPException(status_code=422, detail='PAPERLESS_BASE_URL fehlt. Bitte im Portainer Stack unter Environment setzen.')
    if not (settings.PAPERLESS_TOKEN or '').strip():
        raise HTTPException(status_code=422, detail='PAPERLESS_TOKEN fehlt. Bitte im Portainer Stack unter Environment setzen.')

    try:
        return await sync_invoices(db, settings)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            raise HTTPException(status_code=502, detail='Paperless Auth failed (401/403). Token prüfen.') from exc
        raise HTTPException(status_code=502, detail=f'Paperless API Fehler ({status}). Base URL/Tag/Token prüfen.') from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f'Paperless nicht erreichbar. PAPERLESS_BASE_URL prüfen ({settings.PAPERLESS_BASE_URL}).') from exc
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("Tag '") and 'nicht gefunden' in message:
            raise HTTPException(
                status_code=404,
                detail=f"{message} (PROJECT_TAG_NAME={settings.PROJECT_TAG_NAME})",
            ) from exc
        raise HTTPException(status_code=422, detail=message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get('/sync/last', response_model=Optional[SyncRunOut])
def last_sync(db: Session = Depends(get_db)):
    last_run = _get_last_sync_run_record(db)
    if last_run is None:
        return None
    return sync_run_to_out(last_run)


@app.get('/sync/runs', response_model=list[SyncRunOut])
def sync_runs(limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)):
    rows = db.scalars(select(SyncRun).order_by(SyncRun.finished_at.desc(), SyncRun.id.desc()).limit(limit)).all()
    return [sync_run_to_out(row) for row in rows]


@app.get('/invoices', response_model=list[InvoiceOut])
def get_invoices(
    needs_review: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(default=None),
    sort: str = Query(default='date_desc'),
    range_key: str = Query(default='month', alias='range'),
    from_value: Optional[str] = Query(default=None, alias='from'),
    to_value: Optional[str] = Query(default=None, alias='to'),
    db: Session = Depends(get_db),
):
    date_range = _resolve_requested_date_range(range_key, from_value, to_value)
    if sort == 'vendor_asc':
        stmt = select(Invoice)
        stmt = apply_date_filter_to_datetime(stmt, Invoice.paperless_created, date_range)
        if needs_review is not None:
            stmt = stmt.where(Invoice.needs_review == needs_review)
        if search:
            like = f'%{search.strip()}%'
            stmt = stmt.where(or_(Invoice.vendor.ilike(like), Invoice.title.ilike(like)))
        stmt = stmt.order_by(Invoice.vendor.asc().nullslast(), Invoice.id.desc())
    else:
        stmt = _build_invoice_stmt(date_range, search=search, needs_review=needs_review, sort=sort)
    rows = db.scalars(stmt).all()
    return [_invoice_to_out(r) for r in rows]


@app.get('/invoices/review', response_model=InvoiceReviewListOut)
def review_invoices(
    sort: str = Query(default='amount_desc'),
    range_key: str = Query(default='month', alias='range'),
    from_value: Optional[str] = Query(default=None, alias='from'),
    to_value: Optional[str] = Query(default=None, alias='to'),
    db: Session = Depends(get_db),
):
    date_range = _resolve_requested_date_range(range_key, from_value, to_value)
    review_sort = _normalize_review_sort(sort)
    rows = db.scalars(_build_invoice_stmt(date_range, needs_review=True, sort=review_sort)).all()
    items = [_invoice_to_out(row) for row in rows]
    return InvoiceReviewListOut(total=len(items), items=items)


@app.put('/invoices/{invoice_id}', response_model=InvoiceOut)
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail='Invoice not found')

    changes = payload.model_dump(exclude_unset=True)
    reset_vendor = bool(changes.pop('reset_vendor', False))
    reset_amount = bool(changes.pop('reset_amount', False))
    if 'amount' in changes and changes['amount'] is not None:
        new_amount = Decimal(str(changes['amount']))
        if invoice.amount != new_amount:
            invoice.amount_source = 'manual'
        invoice.amount = new_amount
    if 'vendor' in changes:
        if changes['vendor'] is not None and invoice.vendor != changes['vendor']:
            invoice.vendor_source = 'manual'
        invoice.vendor = changes['vendor']

    if reset_vendor:
        invoice.vendor_source = 'auto'
        if invoice.vendor_auto is not None:
            invoice.vendor = invoice.vendor_auto
    if reset_amount:
        invoice.amount_source = 'auto'
        if invoice.amount_auto is not None:
            invoice.amount = invoice.amount_auto

    if 'needs_review' in changes:
        invoice.needs_review = bool(changes['needs_review'])
    elif ('vendor' in changes or 'amount' in changes or reset_vendor or reset_amount):
        if invoice.vendor and invoice.amount is not None:
            invoice.needs_review = False
        elif invoice.vendor_source == 'auto' and invoice.amount_source == 'auto':
            invoice.needs_review = True

    db.commit()
    db.refresh(invoice)
    return _invoice_to_out(invoice)


@app.patch('/invoices/{invoice_id}/resolve', response_model=InvoiceOut)
def resolve_invoice_review(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail='Invoice not found')
    invoice.needs_review = False
    db.commit()
    db.refresh(invoice)
    return _invoice_to_out(invoice)


@app.post('/manual-costs', response_model=ManualCostOut)
def create_manual_cost(payload: ManualCostCreate, db: Session = Depends(get_db)):
    settings = get_settings()
    item = ManualCost(
        source='manual',
        date=payload.date or date.today(),
        vendor=payload.vendor,
        amount=Decimal(str(payload.amount)),
        currency=payload.currency or settings.DEFAULT_CURRENCY,
        category=payload.category,
        note=payload.note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _manual_to_out(item)


@app.get('/manual-costs', response_model=list[ManualCostOut])
def list_manual_costs(
    range_key: str = Query(default='month', alias='range'),
    from_value: Optional[str] = Query(default=None, alias='from'),
    to_value: Optional[str] = Query(default=None, alias='to'),
    archived: str = Query(default='active'),
    db: Session = Depends(get_db),
):
    date_range = _resolve_requested_date_range(range_key, from_value, to_value)
    stmt = _build_manual_stmt(date_range, archived=archived)
    rows = db.scalars(stmt).all()
    return [_manual_to_out(r) for r in rows]


@app.put('/manual-costs/{item_id}', response_model=ManualCostOut)
def update_manual_cost(item_id: int, payload: ManualCostUpdate, db: Session = Depends(get_db)):
    item = db.get(ManualCost, item_id)
    if not item:
        raise HTTPException(status_code=404, detail='Manual cost not found')
    changes = payload.model_dump(exclude_unset=True)
    for key in ('date', 'vendor', 'currency', 'category', 'note'):
        if key in changes:
            setattr(item, key, changes[key])
    if 'amount' in changes and changes['amount'] is not None:
        item.amount = Decimal(str(changes['amount']))
    db.commit()
    db.refresh(item)
    return _manual_to_out(item)


@app.patch('/manual-costs/{item_id}/archive', response_model=ManualCostOut)
def archive_manual_cost(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ManualCost, item_id)
    if not item:
        raise HTTPException(status_code=404, detail='Manual cost not found')
    item.is_archived = True
    item.archived_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _manual_to_out(item)


@app.patch('/manual-costs/{item_id}/restore', response_model=ManualCostOut)
def restore_manual_cost(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ManualCost, item_id)
    if not item:
        raise HTTPException(status_code=404, detail='Manual cost not found')
    item.is_archived = False
    item.archived_at = None
    db.commit()
    db.refresh(item)
    return _manual_to_out(item)


@app.get('/summary', response_model=SummaryOut)
def summary(
    range_key: str = Query(default='month', alias='range'),
    from_value: Optional[str] = Query(default=None, alias='from'),
    to_value: Optional[str] = Query(default=None, alias='to'),
    db: Session = Depends(get_db),
):
    date_range = _resolve_requested_date_range(range_key, from_value, to_value)
    invoice_sum_stmt = select(func.coalesce(func.sum(Invoice.amount), 0))
    invoice_sum_stmt = apply_date_filter_to_datetime(invoice_sum_stmt, Invoice.paperless_created, date_range)
    manual_sum_stmt = select(func.coalesce(func.sum(ManualCost.amount), 0))
    manual_sum_stmt = apply_date_filter_to_date(manual_sum_stmt, ManualCost.date, date_range)
    manual_sum_stmt = manual_sum_stmt.where(ManualCost.is_archived.is_(False))

    invoice_count_stmt = select(func.count()).select_from(Invoice)
    invoice_count_stmt = apply_date_filter_to_datetime(invoice_count_stmt, Invoice.paperless_created, date_range)
    manual_count_stmt = select(func.count()).select_from(ManualCost)
    manual_count_stmt = apply_date_filter_to_date(manual_count_stmt, ManualCost.date, date_range)
    manual_count_stmt = manual_count_stmt.where(ManualCost.is_archived.is_(False))
    needs_review_stmt = select(func.count()).select_from(Invoice).where(Invoice.needs_review.is_(True))
    needs_review_stmt = apply_date_filter_to_datetime(needs_review_stmt, Invoice.paperless_created, date_range)

    paperless_total = float(db.scalar(invoice_sum_stmt) or 0)
    manual_total = float(db.scalar(manual_sum_stmt) or 0)
    invoice_count = int(db.scalar(invoice_count_stmt) or 0)
    manual_cost_count = int(db.scalar(manual_count_stmt) or 0)
    needs_review_count = int(db.scalar(needs_review_stmt) or 0)

    top_vendor_stmt = (
        select(Invoice.vendor, func.coalesce(func.sum(Invoice.amount), 0).label('amount'))
        .where(Invoice.vendor.is_not(None))
        .group_by(Invoice.vendor)
        .order_by(func.sum(Invoice.amount).desc())
        .limit(10)
    )
    top_vendor_stmt = apply_date_filter_to_datetime(top_vendor_stmt, Invoice.paperless_created, date_range)
    top_vendor_rows = db.execute(top_vendor_stmt).all()
    top_vendors = [{'name': row[0], 'amount': float(row[1] or 0)} for row in top_vendor_rows if row[0]]

    category_stmt = (
        select(ManualCost.category, func.coalesce(func.sum(ManualCost.amount), 0).label('amount'))
        .where(ManualCost.is_archived.is_(False))
        .group_by(ManualCost.category)
        .order_by(func.sum(ManualCost.amount).desc())
    )
    category_stmt = apply_date_filter_to_date(category_stmt, ManualCost.date, date_range)
    category_rows = db.execute(category_stmt).all()
    categories = [
        {'category': row[0] or 'Unkategorisiert', 'amount': float(row[1] or 0)}
        for row in category_rows
    ]

    return SummaryOut(
        total_amount=round(paperless_total + manual_total, 2),
        paperless_total=round(paperless_total, 2),
        manual_total=round(manual_total, 2),
        invoice_count=invoice_count,
        manual_cost_count=manual_cost_count,
        needs_review_count=needs_review_count,
        top_vendors=top_vendors,
        costs_by_category=categories,
    )


@app.get('/export.csv')
def export_csv(
    range_key: str = Query(default='month', alias='range'),
    from_value: Optional[str] = Query(default=None, alias='from'),
    to_value: Optional[str] = Query(default=None, alias='to'),
    search: Optional[str] = Query(default=None),
    needs_review: str = Query(default='all'),
    source: str = Query(default='all'),
    sort: str = Query(default='date_desc'),
    archived: str = Query(default='active'),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    date_range = _resolve_requested_date_range(range_key, from_value, to_value)
    source_filter = _normalize_source_filter(source)
    archived_filter = _normalize_archived_filter(archived)
    needs_review_filter = _normalize_export_needs_review(needs_review)
    sort_key = _normalize_sort(sort)

    rows: list[dict[str, object | None]] = []

    if source_filter in {'all', 'paperless'}:
        invoice_rows = db.scalars(
            _build_invoice_stmt(date_range, search=search, needs_review=needs_review_filter, sort=sort_key)
        ).all()
        for invoice in invoice_rows:
            rows.append(
                {
                    'date': invoice.paperless_created.date().isoformat() if invoice.paperless_created else '',
                    'source': 'paperless',
                    'company': invoice.vendor or '',
                    'title': invoice.title or '',
                    'amount_gross': float(invoice.amount) if invoice.amount is not None else '',
                    'currency': invoice.currency or '',
                    'needs_review': invoice.needs_review,
                    'confidence': invoice.confidence,
                    'project_name': settings.PROJECT_NAME,
                    'project_tag': settings.PROJECT_TAG_NAME,
                    'paperless_doc_id': invoice.paperless_doc_id,
                    'paperless_url': _paperless_document_url(settings, invoice.paperless_doc_id),
                    'notes': '',
                    '_sort_date': invoice.paperless_created or datetime.min,
                    '_sort_amount': float(invoice.amount) if invoice.amount is not None else 0.0,
                }
            )

    if source_filter in {'all', 'manual'} and needs_review_filter is None:
        manual_rows = db.scalars(
            _build_manual_stmt(date_range, archived=archived_filter, search=search, sort=sort_key)
        ).all()
        for item in manual_rows:
            rows.append(
                {
                    'date': item.date.isoformat(),
                    'source': 'manual',
                    'company': item.vendor,
                    'title': '',
                    'amount_gross': float(item.amount),
                    'currency': item.currency,
                    'needs_review': '',
                    'confidence': '',
                    'project_name': settings.PROJECT_NAME,
                    'project_tag': settings.PROJECT_TAG_NAME,
                    'paperless_doc_id': '',
                    'paperless_url': '',
                    'notes': item.note or '',
                    '_sort_date': datetime.combine(item.date, datetime.min.time()),
                    '_sort_amount': float(item.amount),
                }
            )

    reverse = sort_key in {'date_desc', 'amount_desc'}
    if sort_key.startswith('amount'):
        rows.sort(key=lambda row: (float(row['_sort_amount'] or 0), str(row['date'] or '')), reverse=reverse)
    else:
        rows.sort(key=lambda row: (row['_sort_date'] or datetime.min, str(row['company'] or '')), reverse=reverse)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'date',
        'source',
        'company',
        'title',
        'amount_gross',
        'currency',
        'needs_review',
        'confidence',
        'project_name',
        'project_tag',
        'paperless_doc_id',
        'paperless_url',
        'notes',
    ])

    for row in rows:
        writer.writerow([
            row['date'] or '',
            row['source'] or '',
            row['company'] or '',
            row['title'] or '',
            row['amount_gross'] if row['amount_gross'] != '' else '',
            row['currency'] or '',
            row['needs_review'] if row['needs_review'] is not None else '',
            row['confidence'] if row['confidence'] is not None else '',
            row['project_name'] or '',
            row['project_tag'] or '',
            row['paperless_doc_id'] if row['paperless_doc_id'] is not None else '',
            row['paperless_url'] or '',
            row['notes'] or '',
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename={_export_filename(settings)}'},
    )
