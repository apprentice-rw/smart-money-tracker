"""
config.py — Application configuration.

Centralises CORS origins, frontend directory, and project root paths.
"""

import os
from pathlib import Path

# Project root is 3 levels up from this file (backend/app/core/config.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

FRONTEND_DIR = Path(os.environ.get("FRONTEND_DIR", str(PROJECT_ROOT / "frontend" / "dist")))

_DEFAULT_ORIGINS = [
    "https://smart-money-tracker-vxr6.vercel.app",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# ALLOWED_ORIGINS env var overrides the default list.
# Set it to a comma-separated list of origins, e.g.:
#   ALLOWED_ORIGINS=https://myapp.vercel.app,https://preview.vercel.app
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins
    else _DEFAULT_ORIGINS
)
