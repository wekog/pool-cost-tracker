from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault('PAPERLESS_TOKEN', 'test-token')
os.environ.setdefault('PAPERLESS_BASE_URL', 'http://paperless.local:8000')

from api.app import main
from api.app.date_ranges import resolve_date_range as resolve_date_range_value
from api.app.database import Base
from api.app.models import Invoice


def _make_db_session():
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def _seed_review_data(db):
    db.add_all(
        [
            Invoice(
                source='paperless',
                paperless_doc_id=101,
                paperless_created=datetime(2026, 2, 10, 9, 0, 0),
                title='Hoher Betrag',
                vendor='Alpha GmbH',
                vendor_auto='Alpha GmbH',
                vendor_source='auto',
                amount=Decimal('300.00'),
                amount_auto=Decimal('300.00'),
                amount_source='auto',
                currency='EUR',
                confidence=0.55,
                needs_review=True,
                extracted_at=datetime.utcnow(),
                debug_json='{}',
            ),
            Invoice(
                source='paperless',
                paperless_doc_id=102,
                paperless_created=datetime(2026, 2, 12, 9, 0, 0),
                title='Neueres Datum',
                vendor='Beta GmbH',
                vendor_auto='Beta GmbH',
                vendor_source='auto',
                amount=Decimal('120.00'),
                amount_auto=Decimal('120.00'),
                amount_source='auto',
                currency='EUR',
                confidence=0.66,
                needs_review=True,
                extracted_at=datetime.utcnow(),
                debug_json='{}',
            ),
            Invoice(
                source='paperless',
                paperless_doc_id=103,
                paperless_created=datetime(2026, 1, 15, 9, 0, 0),
                title='Alter Monat',
                vendor='Gamma GmbH',
                vendor_auto='Gamma GmbH',
                vendor_source='auto',
                amount=Decimal('500.00'),
                amount_auto=Decimal('500.00'),
                amount_source='auto',
                currency='EUR',
                confidence=0.77,
                needs_review=True,
                extracted_at=datetime.utcnow(),
                debug_json='{}',
            ),
            Invoice(
                source='paperless',
                paperless_doc_id=104,
                paperless_created=datetime(2026, 2, 14, 9, 0, 0),
                title='Schon geprüft',
                vendor='Delta GmbH',
                vendor_auto='Delta GmbH',
                vendor_source='auto',
                amount=Decimal('999.00'),
                amount_auto=Decimal('999.00'),
                amount_source='auto',
                currency='EUR',
                confidence=0.95,
                needs_review=False,
                extracted_at=datetime.utcnow(),
                debug_json='{}',
            ),
        ]
    )
    db.commit()


def test_review_inbox_filters_by_range_and_sorts_by_amount(monkeypatch):
    db = _make_db_session()
    _seed_review_data(db)
    monkeypatch.setattr(
        main,
        'resolve_date_range',
        lambda range_key='month', from_value=None, to_value=None: resolve_date_range_value(
            range_key, from_value, to_value, today=date(2026, 2, 20)
        ),
    )

    response = main.review_invoices(sort='amount_desc', range_key='month', from_value=None, to_value=None, db=db)

    assert response.total == 2
    assert [item.paperless_doc_id for item in response.items] == [101, 102]


def test_review_inbox_sorts_by_date_desc(monkeypatch):
    db = _make_db_session()
    _seed_review_data(db)
    monkeypatch.setattr(
        main,
        'resolve_date_range',
        lambda range_key='month', from_value=None, to_value=None: resolve_date_range_value(
            range_key, from_value, to_value, today=date(2026, 2, 20)
        ),
    )

    response = main.review_invoices(sort='date_desc', range_key='month', from_value=None, to_value=None, db=db)

    assert response.total == 2
    assert [item.paperless_doc_id for item in response.items] == [102, 101]


def test_resolve_invoice_review_marks_invoice_as_done():
    db = _make_db_session()
    _seed_review_data(db)
    invoice = db.query(Invoice).filter(Invoice.paperless_doc_id == 101).one()

    resolved = main.resolve_invoice_review(invoice.id, db)

    assert resolved.needs_review is False
    db.refresh(invoice)
    assert invoice.needs_review is False


def test_review_inbox_rejects_invalid_sort():
    db = _make_db_session()
    _seed_review_data(db)

    with pytest.raises(HTTPException) as exc:
        main.review_invoices(sort='amount_asc', range_key='all', from_value=None, to_value=None, db=db)

    assert exc.value.status_code == 422
