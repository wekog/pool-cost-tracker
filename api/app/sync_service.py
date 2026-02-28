from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .extraction import extract_invoice_fields
from .models import Invoice, SyncRun
from .paperless import PaperlessClient
from .schemas import SyncErrorOut, SyncResponse, SyncRunOut
from .settings import Settings


async def sync_invoices(db: Session, settings: Settings) -> SyncResponse:
    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    client = PaperlessClient(settings)
    tag_id = await client.get_tag_id_by_name()
    docs = await client.get_project_documents(tag_id)

    existing = {}
    if docs:
        doc_ids = [int(doc['id']) for doc in docs if doc.get('id') is not None]
        if doc_ids:
            existing = {
                row.paperless_doc_id: row
                for row in db.scalars(select(Invoice).where(Invoice.paperless_doc_id.in_(doc_ids))).all()
            }

    inserted = updated = skipped = error_count = 0
    first_error_text: str | None = None
    now = datetime.utcnow()

    for doc in docs:
        try:
            if doc.get('id') is None:
                continue
            extracted = extract_invoice_fields(doc.get('content') or '', doc.get('correspondent'))
            inv = existing.get(int(doc['id']))

            paperless_created = None
            if doc.get('created'):
                try:
                    paperless_created = datetime.fromisoformat(str(doc['created']).replace('Z', '+00:00'))
                except ValueError:
                    paperless_created = None

            extracted_vendor = extracted.get('vendor')
            extracted_amount = Decimal(str(extracted['amount'])) if extracted.get('amount') is not None else None
            new_data = {
                'source': 'paperless',
                'paperless_doc_id': int(doc['id']),
                'paperless_created': paperless_created,
                'title': doc.get('title'),
                'vendor_auto': extracted_vendor,
                'amount_auto': extracted_amount,
                'currency': extracted.get('currency', 'EUR'),
                'confidence': float(extracted.get('confidence') or 0.0),
                'extracted_at': now,
                'debug_json': extracted.get('debug_json'),
                'correspondent': doc.get('correspondent'),
                'document_type': doc.get('document_type'),
                'ocr_text': doc.get('content') or '',
            }

            if inv is None:
                new_data['vendor'] = extracted_vendor
                new_data['amount'] = extracted_amount
                new_data['vendor_source'] = 'auto'
                new_data['amount_source'] = 'auto'
                new_data['needs_review'] = bool(extracted.get('needs_review', True))
                db.add(Invoice(**new_data))
                inserted += 1
                continue

            changed = False

            if inv.vendor_source == 'auto':
                new_data['vendor'] = extracted_vendor
            if inv.amount_source == 'auto':
                new_data['amount'] = extracted_amount

            # Manual overrides should not be reverted to review-required by sync.
            if inv.vendor_source == 'manual' or inv.amount_source == 'manual':
                new_data['needs_review'] = False
            else:
                new_data['needs_review'] = bool(extracted.get('needs_review', True))

            for key, value in new_data.items():
                if getattr(inv, key) != value:
                    setattr(inv, key, value)
                    changed = True
            if changed:
                updated += 1
            else:
                skipped += 1
        except Exception as exc:  # pragma: no cover - defensive guard for malformed OCR rows
            error_count += 1
            if first_error_text is None:
                first_error_text = str(exc)

    finished_at = datetime.now(timezone.utc)
    duration_ms = int((perf_counter() - started) * 1000)
    sync_run = SyncRun(
        started_at=started_at.replace(tzinfo=None),
        finished_at=finished_at.replace(tzinfo=None),
        duration_ms=duration_ms,
        checked_docs=len(docs),
        new_invoices=inserted,
        updated_invoices=updated,
        skipped_invoices=skipped,
        error_count=error_count,
        last_error_text=first_error_text,
    )
    db.add(sync_run)
    db.commit()
    return SyncResponse(
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        checked_docs=len(docs),
        new_invoices=inserted,
        updated_invoices=updated,
        skipped_invoices=skipped,
        errors=SyncErrorOut(count=error_count, first_error=first_error_text),
    )


def sync_run_to_out(sync_run: SyncRun) -> SyncRunOut:
    return SyncRunOut(
        id=sync_run.id,
        started_at=sync_run.started_at,
        finished_at=sync_run.finished_at,
        duration_ms=sync_run.duration_ms,
        checked_docs=sync_run.checked_docs,
        new_invoices=sync_run.new_invoices,
        updated_invoices=sync_run.updated_invoices,
        skipped_invoices=sync_run.skipped_invoices,
        errors=SyncErrorOut(count=sync_run.error_count, first_error=sync_run.last_error_text),
    )
