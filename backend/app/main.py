"""
main.py — FastAPI application factory.

Creates the app, configures CORS, includes all routers, mounts static files.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import ALLOWED_ORIGINS, FRONTEND_DIR
from backend.app.api.routes import health, institutions, stocks, tickers, consensus

app = FastAPI(
    title="Smart Money Tracker API",
    description="13F holdings data for institutional investors",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(health.router)
app.include_router(tickers.router)
app.include_router(institutions.router)
app.include_router(stocks.router)
app.include_router(consensus.router)

# Serve the built React frontend at /app.
# Run `cd frontend && npm run build` first to populate frontend/dist/.
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
