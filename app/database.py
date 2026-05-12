from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

DB_URL = f"sqlite:///{settings.db_path}"

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate_schema()


def _migrate_schema():
    """Idempotently add columns to existing tables (SQLite-friendly)."""
    needed = {
        "photos": [
            ("favorite", "INTEGER DEFAULT 0"),
            ("rating", "INTEGER DEFAULT 0"),
            ("phash", "VARCHAR(16)"),
            ("gps_lat", "REAL"),
            ("gps_lon", "REAL"),
        ],
    }
    with engine.begin() as conn:
        for table, cols in needed.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for name, ddl in cols:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        # Helpful indexes for new columns
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_photos_phash ON photos(phash)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_photos_favorite ON photos(favorite)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_photos_rating ON photos(rating)")
