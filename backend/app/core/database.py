"""
database.py — SQLAlchemy engine factory.

Reads DATABASE_URL from the environment (via .env for local dev).
Supports both SQLite (local) and PostgreSQL (production on Railway).
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event

load_dotenv()

_DB_URL = os.environ.get("DATABASE_URL", "sqlite:///smart_money.db")

# Railway (and some older tools) emit postgres:// — SQLAlchemy needs postgresql://
if _DB_URL.startswith("postgres://"):
    _DB_URL = _DB_URL.replace("postgres://", "postgresql+psycopg2://", 1)

IS_SQLITE = _DB_URL.startswith("sqlite")

engine = create_engine(
    _DB_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    pool_pre_ping=True,  # detects stale connections (important on Railway)
    future=True,         # 2.0-style: enables conn.commit() / conn.rollback()
)


if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()
