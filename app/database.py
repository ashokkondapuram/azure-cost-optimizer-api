from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./azurefinops.db")

# For SQLite: enable WAL mode for better concurrent read performance
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
    pool_size=10 if not DATABASE_URL.startswith("sqlite") else 1,
    max_overflow=20 if not DATABASE_URL.startswith("sqlite") else 0,
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")   # concurrent reads
        cursor.execute("PRAGMA synchronous=NORMAL") # faster writes
        cursor.execute("PRAGMA cache_size=-64000")  # 64 MB page cache
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called on startup."""
    from .models import Base
    Base.metadata.create_all(bind=engine)
