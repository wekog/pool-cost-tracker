import asyncio
import os
import sys
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault('PAPERLESS_TOKEN', 'test-token')
os.environ.setdefault('PAPERLESS_BASE_URL', 'http://paperless.local:8000')

if sys.version_info < (3, 10):
    pytest.skip('Manual sync source tests target runtime Python 3.10+ (Docker uses 3.12)', allow_module_level=True)

from api.app import sync_service
from api.app.main import update_invoice
from api.app.models import Invoice
from api.app.schemas import InvoiceUpdate
from api.app.settings import Settings
from api.app.database import Base


def _make_db_session():
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def _settings() -> Settings:
    return Settings(PAPERLESS_TOKEN='dummy-token', PAPERLESS_BASE_URL='http://paperless.local:8000', PROJECT_TAG_NAME='Pool')


def _install_fake_sync(monkeypatch, extracted_vendor='Auto GmbH', extracted_amount=123.45):
    class FakePaperlessClient:
        def __init__(self, settings):
            self.settings = settings

        async def get_tag_id_by_name(self):
            return 99

        async def get_project_documents(self, pool_tag_id: int):
            return [
                {
                    'id': 1,
                    'title': 'Rechnung 1',
                    'created': '2026-01-15T10:00:00Z',
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
            'vendor': extracted_vendor,
            'amount': extracted_amount,
            'currency': 'EUR',
            'confidence': 0.88,
            'needs_review': False,
            'debug_json': '{"source":"test"}',
        },
    )


def test_sync_inserts_auto_sources(monkeypatch):
    _install_fake_sync(monkeypatch)
    db = _make_db_session()

    asyncio.run(sync_service.sync_invoices(db, _settings()))

    inv = db.scalar(select(Invoice).where(Invoice.paperless_doc_id == 1))
    assert inv is not None
    assert inv.vendor == 'Auto GmbH'
    assert inv.vendor_auto == 'Auto GmbH'
    assert float(inv.amount) == 123.45
    assert float(inv.amount_auto) == 123.45
    assert inv.vendor_source == 'auto'
    assert inv.amount_source == 'auto'


def test_update_invoice_sets_manual_sources():
    db = _make_db_session()
    invoice = Invoice(
        source='paperless',
        paperless_doc_id=1,
        paperless_created=datetime.utcnow(),
        title='Test',
        vendor='Auto GmbH',
        vendor_source='auto',
        amount=Decimal('100.00'),
        amount_source='auto',
        currency='EUR',
        confidence=0.8,
        needs_review=True,
        extracted_at=datetime.utcnow(),
        debug_json='{}',
    )
    db.add(invoice)
    db.commit()

    update_invoice(invoice.id, InvoiceUpdate(vendor='Manuell GmbH'), db)
    update_invoice(invoice.id, InvoiceUpdate(amount=333.33), db)

    refreshed = db.get(Invoice, invoice.id)
    assert refreshed.vendor == 'Manuell GmbH'
    assert refreshed.vendor_source == 'manual'
    assert float(refreshed.amount) == 333.33
    assert refreshed.amount_source == 'manual'


def test_sync_preserves_manual_vendor(monkeypatch):
    _install_fake_sync(monkeypatch, extracted_vendor='Auto überschrieben GmbH', extracted_amount=222.22)
    db = _make_db_session()
    invoice = Invoice(
        source='paperless',
        paperless_doc_id=1,
        paperless_created=datetime.utcnow(),
        title='Test',
        vendor='Mein Unternehmen',
        vendor_source='manual',
        amount=Decimal('100.00'),
        amount_source='auto',
        currency='EUR',
        confidence=0.8,
        needs_review=False,
        extracted_at=datetime.utcnow(),
        debug_json='{}',
    )
    db.add(invoice)
    db.commit()

    asyncio.run(sync_service.sync_invoices(db, _settings()))

    refreshed = db.get(Invoice, invoice.id)
    assert refreshed.vendor == 'Mein Unternehmen'
    assert refreshed.vendor_auto == 'Auto überschrieben GmbH'
    assert refreshed.vendor_source == 'manual'
    assert float(refreshed.amount) == 222.22
    assert float(refreshed.amount_auto) == 222.22
    assert refreshed.needs_review is False


def test_sync_preserves_manual_amount(monkeypatch):
    _install_fake_sync(monkeypatch, extracted_vendor='Auto Vendor GmbH', extracted_amount=444.44)
    db = _make_db_session()
    invoice = Invoice(
        source='paperless',
        paperless_doc_id=1,
        paperless_created=datetime.utcnow(),
        title='Test',
        vendor='Alt Vendor',
        vendor_source='auto',
        amount=Decimal('999.99'),
        amount_source='manual',
        currency='EUR',
        confidence=0.8,
        needs_review=False,
        extracted_at=datetime.utcnow(),
        debug_json='{}',
    )
    db.add(invoice)
    db.commit()

    asyncio.run(sync_service.sync_invoices(db, _settings()))

    refreshed = db.get(Invoice, invoice.id)
    assert refreshed.vendor == 'Auto Vendor GmbH'
    assert refreshed.vendor_auto == 'Auto Vendor GmbH'
    assert float(refreshed.amount) == 999.99
    assert float(refreshed.amount_auto) == 444.44
    assert refreshed.amount_source == 'manual'
    assert refreshed.needs_review is False
