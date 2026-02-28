import os

from sqlalchemy import create_engine, inspect, text

os.environ.setdefault('PAPERLESS_TOKEN', 'test-token')
os.environ.setdefault('PAPERLESS_BASE_URL', 'http://paperless.local:8000')

from api.app.database import ensure_schema_compatibility


def test_ensure_schema_compatibility_adds_missing_invoice_columns():
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE invoices (
                    id INTEGER PRIMARY KEY,
                    source VARCHAR(32) NOT NULL,
                    paperless_doc_id INTEGER NOT NULL,
                    paperless_created DATETIME,
                    title TEXT,
                    vendor VARCHAR(255),
                    amount NUMERIC(12, 2),
                    currency VARCHAR(8) NOT NULL,
                    confidence FLOAT NOT NULL,
                    needs_review BOOLEAN NOT NULL,
                    extracted_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    debug_json TEXT,
                    correspondent VARCHAR(255),
                    document_type VARCHAR(255),
                    ocr_text TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO invoices (
                    id, source, paperless_doc_id, paperless_created, title, vendor, amount,
                    currency, confidence, needs_review, extracted_at, updated_at
                ) VALUES (
                    1, 'paperless', 100, '2026-02-28 12:00:00', 'Test', 'Auto GmbH', 123.45,
                    'EUR', 0.9, 0, '2026-02-28 12:00:00', '2026-02-28 12:00:00'
                )
                """
            )
        )

    ensure_schema_compatibility(engine)

    inspector = inspect(engine)
    columns = {column['name'] for column in inspector.get_columns('invoices')}

    assert 'vendor_source' in columns
    assert 'amount_source' in columns
    assert 'vendor_auto' in columns
    assert 'amount_auto' in columns

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT vendor_source, amount_source, vendor_auto, amount_auto
                FROM invoices
                WHERE id = 1
                """
            )
        ).one()

    assert row.vendor_source == 'auto'
    assert row.amount_source == 'auto'
    assert row.vendor_auto == 'Auto GmbH'
    assert float(row.amount_auto) == 123.45
