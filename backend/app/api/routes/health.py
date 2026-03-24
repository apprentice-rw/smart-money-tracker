"""GET /health — database connectivity check."""

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from backend.app.api.deps import get_conn
from backend.app.core.database import engine

router = APIRouter()


@router.get("/health", tags=["meta"])
def health(conn: Connection = Depends(get_conn)) -> dict:
    """
    Returns database row counts for all tables.
    Useful for confirming the DB is populated and the API can reach it.
    """
    counts = {
        "institutions":     conn.execute(text("SELECT COUNT(*) FROM institutions")).scalar(),
        "filings":          conn.execute(text("SELECT COUNT(*) FROM filings")).scalar(),
        "holdings":         conn.execute(text("SELECT COUNT(*) FROM holdings")).scalar(),
        "position_changes": conn.execute(text("SELECT COUNT(*) FROM position_changes")).scalar(),
    }
    return {
        "status": "ok",
        "database": engine.url.drivername.split("+")[0],
        "row_counts": counts,
    }
