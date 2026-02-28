import asyncio
import csv
import os
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault('PAPERLESS_TOKEN', 'test-token')
os.environ.setdefault('PAPERLESS_BASE_URL', 'http://paperless.local:8000')

from api.app import main, sync_service
from api.app.date_ranges import resolve_date_range as resolve_date_range_value
from api.app.database import Base
from api.app.models import Invoice, ManualCost, SyncRun
from api.app.schemas import InvoiceUpdate
from api.app.settings import Settings


def _make_db_session():
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def _seed_range_data(db):
    db.add_all(
        [
            Invoice(
                source='paperless',
                paperless_doc_id=1,
                paperless_created=datetime(2026, 2, 10, 10, 0, 0),
                title='Februar',
                vendor='Feb AG',
                vendor_auto='Feb AG',
                vendor_source='auto',
                amount=Decimal('100.00'),
                amount_auto=Decimal('100.00'),
                amount_source='auto',
                currency='EUR',
                confidence=0.8,
                needs_review=False,
                extracted_at=datetime.utcnow(),
                debug_json='{}',
            ),
            Invoice(
                source='paperless',
                paperless_doc_id=2,
                paperless_created=datetime(2026, 1, 10, 10, 0, 0),
                title='Januar',
                vendor='Jan AG',
                vendor_auto='Jan AG',
                vendor_source='auto',
                amount=Decimal('200.00'),
                amount_auto=Decimal('200.00'),
                amount_source='auto',
                currency='EUR',
                confidence=0.8,
                needs_review=False,
                extracted_at=datetime.utcnow(),
                debug_json='{}',
            ),
        ]
    )
    db.add_all(
        [
            ManualCost(
                source='manual',
                date=date(2026, 2, 12),
                vendor='Feb Manuell',
                amount=Decimal('50.00'),
                currency='EUR',
                category='Technik',
            ),
            ManualCost(
                source='manual',
                date=date(2025, 12, 12),
                vendor='Alt Manuell',
                amount=Decimal('75.00'),
                currency='EUR',
                category='Alt',
            ),
        ]
    )
    db.commit()


async def _collect_stream(response) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode('utf-8') if isinstance(chunk, bytes) else str(chunk))
    return ''.join(chunks)


def test_summary_and_lists_apply_range_filters(monkeypatch):
    db = _make_db_session()
    _seed_range_data(db)
    monkeypatch.setattr(
        main,
        'resolve_date_range',
        lambda range_key='month', from_value=None, to_value=None: resolve_date_range_value(
            range_key, from_value, to_value, today=date(2026, 2, 15)
        ),
    )

    summary = main.summary(range_key='month', from_value=None, to_value=None, db=db)
    invoices = main.get_invoices(
        needs_review=None,
        search=None,
        sort='date_desc',
        range_key='month',
        from_value=None,
        to_value=None,
        db=db,
    )
    manual_costs = main.list_manual_costs(range_key='month', from_value=None, to_value=None, db=db)

    assert summary.paperless_total == 100.0
    assert summary.manual_total == 50.0
    assert summary.total_amount == 150.0
    assert len(invoices) == 1
    assert invoices[0].paperless_doc_id == 1
    assert len(manual_costs) == 1
    assert manual_costs[0].vendor == 'Feb Manuell'


def test_custom_range_filters_export(monkeypatch):
    db = _make_db_session()
    _seed_range_data(db)
    monkeypatch.setattr(
        main,
        'resolve_date_range',
        lambda range_key='month', from_value=None, to_value=None: resolve_date_range_value(
            range_key, from_value, to_value, today=date(2026, 2, 15)
        ),
    )

    response = main.export_csv(range_key='custom', from_value='2026-01-01', to_value='2026-01-31', db=db)
    payload = asyncio.run(_collect_stream(response))
    rows = list(csv.DictReader(payload.splitlines()))

    assert len(rows) == 1
    assert rows[0]['company'] == 'Jan AG'


def test_update_invoice_can_reset_fields_to_auto():
    db = _make_db_session()
    invoice = Invoice(
        source='paperless',
        paperless_doc_id=10,
        paperless_created=datetime.utcnow(),
        title='Reset Test',
        vendor='Manuell GmbH',
        vendor_auto='Auto GmbH',
        vendor_source='manual',
        amount=Decimal('999.00'),
        amount_auto=Decimal('123.45'),
        amount_source='manual',
        currency='EUR',
        confidence=0.7,
        needs_review=False,
        extracted_at=datetime.utcnow(),
        debug_json='{}',
    )
    db.add(invoice)
    db.commit()

    result = main.update_invoice(invoice.id, InvoiceUpdate(reset_vendor=True, reset_amount=True), db)

    assert result.vendor == 'Auto GmbH'
    assert result.vendor_source == 'auto'
    assert result.amount == 123.45
    assert result.amount_source == 'auto'


def test_sync_returns_transparent_result_and_persists_last_run(monkeypatch):
    db = _make_db_session()

    class FakePaperlessClient:
        def __init__(self, settings):
            self.settings = settings

        async def get_tag_id_by_name(self):
            return 99

        async def get_project_documents(self, tag_id: int):
            return [
                {
                    'id': 1,
                    'title': 'Rechnung 1',
                    'created': '2026-02-15T10:00:00Z',
                    'correspondent': 'Correspondent GmbH',
                    'content': 'Brutto 123,45 EUR',
                    'document_type': 'Rechnung',
                }
            ]

    monkeypatch.setattr(sync_service, 'PaperlessClient', FakePaperlessClient)
    monkeypatch.setattr(
        sync_service,
        'extract_invoice_fields',
        lambda text, correspondent: {
            'vendor': 'Auto GmbH',
            'amount': 123.45,
            'currency': 'EUR',
            'confidence': 0.88,
            'needs_review': False,
            'debug_json': '{"source":"test"}',
        },
    )

    result = asyncio.run(
        sync_service.sync_invoices(
            db,
            Settings(PAPERLESS_TOKEN='dummy-token', PAPERLESS_BASE_URL='http://paperless.local:8000', PROJECT_TAG_NAME='Pool'),
        )
    )

    assert result.checked_docs == 1
    assert result.new_invoices == 1
    assert result.updated_invoices == 0
    assert result.skipped_invoices == 0
    assert result.duration_ms >= 0
    assert result.errors.count == 0

    last_run = db.query(SyncRun).order_by(SyncRun.id.desc()).first()
    assert last_run is not None
    assert last_run.checked_docs == 1

    last_sync = main.last_sync(db=db)
    assert last_sync is not None
    assert last_sync.checked_docs == 1
