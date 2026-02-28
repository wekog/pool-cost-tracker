import asyncio
import csv
import os
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault('PAPERLESS_TOKEN', 'test-token')
os.environ.setdefault('PAPERLESS_BASE_URL', 'http://paperless.local:8000')
os.environ.setdefault('PROJECT_NAME', 'Pool')
os.environ.setdefault('PROJECT_TAG_NAME', 'Pool')

from api.app import main
from api.app.database import Base
from api.app.models import Invoice, ManualCost, SyncRun


def _make_db_session():
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


async def _collect_stream(response) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode('utf-8') if isinstance(chunk, bytes) else str(chunk))
    return ''.join(chunks)


def _seed_phase2_data(db):
    db.add_all(
        [
            Invoice(
                source='paperless',
                paperless_doc_id=11,
                paperless_created=datetime(2026, 2, 5, 10, 0, 0),
                title='Needs Review Doc',
                vendor='Review GmbH',
                vendor_auto='Review GmbH',
                vendor_source='auto',
                amount=Decimal('101.00'),
                amount_auto=Decimal('101.00'),
                amount_source='auto',
                currency='EUR',
                confidence=0.5,
                needs_review=True,
                extracted_at=datetime.utcnow(),
                debug_json='{}',
            ),
            Invoice(
                source='paperless',
                paperless_doc_id=12,
                paperless_created=datetime(2026, 2, 6, 10, 0, 0),
                title='Clean Doc',
                vendor='Clean GmbH',
                vendor_auto='Clean GmbH',
                vendor_source='auto',
                amount=Decimal('202.00'),
                amount_auto=Decimal('202.00'),
                amount_source='auto',
                currency='EUR',
                confidence=0.9,
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
                date=date(2026, 2, 7),
                vendor='Active Manual',
                amount=Decimal('50.00'),
                currency='EUR',
                category='Technik',
                note='active note',
                is_archived=False,
            ),
            ManualCost(
                source='manual',
                date=date(2026, 2, 8),
                vendor='Archived Manual',
                amount=Decimal('75.00'),
                currency='EUR',
                category='Archiv',
                note='archived note',
                is_archived=True,
                archived_at=datetime(2026, 2, 9, 12, 0, 0),
            ),
        ]
    )
    db.commit()


def test_export_csv_filters_by_needs_review_and_source(monkeypatch):
    db = _make_db_session()
    _seed_phase2_data(db)

    response = main.export_csv(
        range_key='all',
        from_value=None,
        to_value=None,
        search=None,
        needs_review='true',
        source='all',
        sort='date_desc',
        archived='active',
        db=db,
    )
    rows = list(csv.DictReader(asyncio.run(_collect_stream(response)).splitlines()))

    assert len(rows) == 1
    assert rows[0]['company'] == 'Review GmbH'
    assert rows[0]['source'] == 'paperless'

    response = main.export_csv(
        range_key='all',
        from_value=None,
        to_value=None,
        search='Manual',
        needs_review='all',
        source='manual',
        sort='date_desc',
        archived='active',
        db=db,
    )
    rows = list(csv.DictReader(asyncio.run(_collect_stream(response)).splitlines()))

    assert len(rows) == 1
    assert rows[0]['company'] == 'Active Manual'
    assert rows[0]['source'] == 'manual'


def test_manual_cost_archive_restore_and_filtering():
    db = _make_db_session()
    _seed_phase2_data(db)
    active_manual = db.query(ManualCost).filter(ManualCost.vendor == 'Active Manual').one()
    archived_manual = db.query(ManualCost).filter(ManualCost.vendor == 'Archived Manual').one()

    archived = main.archive_manual_cost(active_manual.id, db)
    assert archived.is_archived is True
    assert archived.archived_at is not None

    active_rows = main.list_manual_costs(range_key='all', from_value=None, to_value=None, archived='active', db=db)
    archived_rows = main.list_manual_costs(range_key='all', from_value=None, to_value=None, archived='archived', db=db)
    all_rows = main.list_manual_costs(range_key='all', from_value=None, to_value=None, archived='all', db=db)

    assert all(row.is_archived is False for row in active_rows)
    assert all(row.is_archived is True for row in archived_rows)
    assert len(all_rows) == 2

    restored = main.restore_manual_cost(archived_manual.id, db)
    assert restored.is_archived is False
    assert restored.archived_at is None


def test_sync_runs_endpoint_returns_latest_rows():
    db = _make_db_session()
    db.add_all(
        [
            SyncRun(
                started_at=datetime(2026, 2, 1, 9, 0, 0),
                finished_at=datetime(2026, 2, 1, 9, 0, 2),
                duration_ms=2000,
                checked_docs=10,
                new_invoices=1,
                updated_invoices=2,
                skipped_invoices=7,
                error_count=0,
                last_error_text=None,
            ),
            SyncRun(
                started_at=datetime(2026, 2, 2, 9, 0, 0),
                finished_at=datetime(2026, 2, 2, 9, 0, 3),
                duration_ms=3000,
                checked_docs=5,
                new_invoices=0,
                updated_invoices=1,
                skipped_invoices=4,
                error_count=1,
                last_error_text='example',
            ),
        ]
    )
    db.commit()

    rows = main.sync_runs(limit=1, db=db)

    assert len(rows) == 1
    assert rows[0].checked_docs == 5
    assert rows[0].errors.count == 1
