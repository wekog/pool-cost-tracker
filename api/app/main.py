from __future__ import annotations

import csv
import io
import json
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .date_ranges import apply_date_filter_to_date, apply_date_filter_to_datetime, resolve_date_range
from .database import Base, SessionLocal, engine, ensure_schema_compatibility, get_db
from .models import Invoice, ManualCost, SyncRun
from .paperless import PaperlessClient
from .queries import all_costs_union_query
from .scheduler import SyncScheduler
from .schemas import ConfigOut, HealthOut, InvoiceOut, InvoiceUpdate, ManualCostCreate, ManualCostOut, ManualCostUpdate, SummaryOut, SyncResponse, SyncRunOut
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
        return resolve_date_range(range_key=range_key, from_value=from_value, to_value=to_value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _get_last_sync_run_record(db: Session) -> Optional[SyncRun]:
    return db.scalar(select(SyncRun).order_by(SyncRun.finished_at.desc(), SyncRun.id.desc()).limit(1))


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
    stmt = select(Invoice)
    stmt = apply_date_filter_to_datetime(stmt, Invoice.paperless_created, date_range)
    if needs_review is not None:
        stmt = stmt.where(Invoice.needs_review == needs_review)
    if search:
        like = f'%{search.strip()}%'
        stmt = stmt.where(or_(Invoice.vendor.ilike(like), Invoice.title.ilike(like)))

    if sort == 'amount_desc':
        stmt = stmt.order_by(Invoice.amount.desc().nullslast(), Invoice.id.desc())
    elif sort == 'amount_asc':
        stmt = stmt.order_by(Invoice.amount.asc().nullsfirst(), Invoice.id.desc())
    elif sort == 'date_asc':
        stmt = stmt.order_by(Invoice.paperless_created.asc().nullsfirst(), Invoice.id.desc())
    elif sort == 'vendor_asc':
        stmt = stmt.order_by(Invoice.vendor.asc().nullslast(), Invoice.id.desc())
    else:
        stmt = stmt.order_by(Invoice.paperless_created.desc().nullslast(), Invoice.id.desc())

    rows = db.scalars(stmt).all()
    return [_invoice_to_out(r) for r in rows]


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


@app.post('/manual-costs', response_model=ManualCostOut)
def create_manual_cost(payload: ManualCostCreate, db: Session = Depends(get_db)):
    item = ManualCost(
        source='manual',
        date=payload.date or date.today(),
        vendor=payload.vendor,
        amount=Decimal(str(payload.amount)),
        currency=payload.currency,
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
    db: Session = Depends(get_db),
):
    date_range = _resolve_requested_date_range(range_key, from_value, to_value)
    stmt = select(ManualCost).order_by(ManualCost.date.desc(), ManualCost.id.desc())
    stmt = apply_date_filter_to_date(stmt, ManualCost.date, date_range)
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


@app.delete('/manual-costs/{item_id}')
def delete_manual_cost(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ManualCost, item_id)
    if not item:
        raise HTTPException(status_code=404, detail='Manual cost not found')
    db.delete(item)
    db.commit()
    return {'deleted': True}


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

    invoice_count_stmt = select(func.count()).select_from(Invoice)
    invoice_count_stmt = apply_date_filter_to_datetime(invoice_count_stmt, Invoice.paperless_created, date_range)
    manual_count_stmt = select(func.count()).select_from(ManualCost)
    manual_count_stmt = apply_date_filter_to_date(manual_count_stmt, ManualCost.date, date_range)
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
    db: Session = Depends(get_db),
):
    date_range = _resolve_requested_date_range(range_key, from_value, to_value)
    union_query = all_costs_union_query(date_range).subquery('all_costs')
    rows = db.execute(select(union_query)).mappings().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'date',
        'source',
        'vendor',
        'amount',
        'currency',
        'title',
        'category',
        'note',
        'paperless_doc_id',
        'confidence',
        'needs_review',
    ])

    for row in rows:
        writer.writerow([
            row['date'] or '',
            row['source'] or '',
            row['vendor'] or '',
            float(row['amount']) if row['amount'] is not None else '',
            row['currency'] or '',
            row['title'] or '',
            row['category'] or '',
            row['note'] or '',
            row['paperless_doc_id'] if row['paperless_doc_id'] is not None else '',
            row['confidence'] if row['confidence'] is not None else '',
            row['needs_review'] if row['needs_review'] is not None else '',
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=pool_costs_export.csv'},
    )
