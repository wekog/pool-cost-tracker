from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .settings import get_settings

settings = get_settings()
connect_args = {'check_same_thread': False} if settings.DATABASE_URL.startswith('sqlite') else {}
engine = create_engine(settings.DATABASE_URL, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def ensure_schema_compatibility(bind) -> None:
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())
    with bind.begin() as connection:
        if 'invoices' in table_names:
            invoice_columns = {column['name'] for column in inspector.get_columns('invoices')}
            statements: list[str] = []

            if 'vendor_source' not in invoice_columns:
                statements.append("ALTER TABLE invoices ADD COLUMN vendor_source VARCHAR(16) NOT NULL DEFAULT 'auto'")
            if 'amount_source' not in invoice_columns:
                statements.append("ALTER TABLE invoices ADD COLUMN amount_source VARCHAR(16) NOT NULL DEFAULT 'auto'")
            if 'vendor_auto' not in invoice_columns:
                statements.append("ALTER TABLE invoices ADD COLUMN vendor_auto VARCHAR(255)")
            if 'amount_auto' not in invoice_columns:
                statements.append("ALTER TABLE invoices ADD COLUMN amount_auto NUMERIC(12, 2)")

            for statement in statements:
                connection.execute(text(statement))

            if 'vendor_source' not in invoice_columns:
                connection.execute(text("UPDATE invoices SET vendor_source='auto' WHERE vendor_source IS NULL OR vendor_source = ''"))
            if 'amount_source' not in invoice_columns:
                connection.execute(text("UPDATE invoices SET amount_source='auto' WHERE amount_source IS NULL OR amount_source = ''"))
            if 'vendor_auto' not in invoice_columns:
                connection.execute(text("UPDATE invoices SET vendor_auto = vendor WHERE vendor_source = 'auto' AND vendor_auto IS NULL"))
            if 'amount_auto' not in invoice_columns:
                connection.execute(text("UPDATE invoices SET amount_auto = amount WHERE amount_source = 'auto' AND amount_auto IS NULL"))

        if 'manual_costs' in table_names:
            manual_columns = {column['name'] for column in inspector.get_columns('manual_costs')}
            if 'is_archived' not in manual_columns:
                connection.execute(text("ALTER TABLE manual_costs ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0"))
                connection.execute(text("UPDATE manual_costs SET is_archived = 0 WHERE is_archived IS NULL"))
            if 'archived_at' not in manual_columns:
                connection.execute(text("ALTER TABLE manual_costs ADD COLUMN archived_at DATETIME"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
