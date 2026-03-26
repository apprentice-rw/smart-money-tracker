# Smart Money Tracker

Track institutional investor positions from SEC 13F filings. Displays quarter-over-quarter changes, cross-institutional consensus signals, and historical stock-level charts for 12 major hedge funds and investment managers.

**Live app:** https://smart-money-tracker-vxr6.vercel.app

---

## Architecture

| Layer    | Technology               | Host           |
|----------|--------------------------|----------------|
| Frontend | React 18 + Vite + Tailwind | Vercel (static SPA) |
| Backend  | FastAPI (Python)         | Render (free tier) |
| Database | PostgreSQL               | Supabase (free tier) |

The frontend is a static SPA deployed to Vercel. It calls the FastAPI backend on Render. The backend reads from a Supabase PostgreSQL database populated by running the ETL pipeline against SEC EDGAR.

---

## Local Development

### Prerequisites

- Python 3.9+
- Node.js 18+

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API (defaults to SQLite if DATABASE_URL is not set)
PYTHONPATH=. uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API will be available at http://127.0.0.1:8000. Interactive docs at http://127.0.0.1:8000/docs.

### Frontend

```bash
cd frontend
npm install
npm run dev   # → http://localhost:5173  (proxies /api calls to :8000)
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values.

| Variable          | Required | Description |
|-------------------|----------|-------------|
| `DATABASE_URL`    | Prod only | Supabase session-pooler connection string. Falls back to `sqlite:///smart_money.db` locally. |
| `ALLOWED_ORIGINS` | Prod only | Comma-separated list of CORS origins (e.g. your Vercel URL). |
| `OPENFIGI_API_KEY`| Optional  | Increases CUSIP resolution throughput from 25 req/min to 250 req/min. |

For Supabase, use the **session pooler** URL (port 5432 from the Supabase dashboard → Settings → Database → Connection string → URI).

For the frontend, set `VITE_API_URL` in the Vercel environment to the Render backend URL (e.g. `https://tidemark-api.onrender.com`).

---

## Populating the Database

The ETL pipeline fetches 8 quarters of 13F filings from SEC EDGAR for 12 institutions and stores holdings + quarter-over-quarter changes in the database.

```bash
# First time (or full refresh) — takes ~10–20 min
DATABASE_URL="<your-supabase-url>" PYTHONPATH=. python backend/scripts/setup_db.py

# After ETL: resolve CUSIPs to tickers (optional, ~2 min with API key)
DATABASE_URL="<your-supabase-url>" PYTHONPATH=. python backend/scripts/resolve_cusips.py --all
```

---

## Running Tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest
```

---

## Project Structure

```
backend/
  app/
    main.py              # FastAPI app factory, CORS, routers
    api/
      deps.py            # get_conn, _require_institution, _resolve_period
      routes/
        health.py        # GET /health
        institutions.py  # GET /institutions, /{id}/filings, /holdings, /changes
        tickers.py       # GET /tickers  (in-memory cache)
        stocks.py        # GET /search, /stock/{cusip}/history
        consensus.py     # GET /consensus/quarters|holdings|buying|selling|emerging|persistent
    services/
      consensus.py       # Shared helpers for consensus routes
    core/
      config.py          # ALLOWED_ORIGINS, FRONTEND_DIR
      database.py        # SQLAlchemy engine (SQLite dev / PostgreSQL prod)
    data/
      sec_edgar.py       # SEC EDGAR fetch + parse logic
      etl.py             # Schema DDL + ETL pipeline
      cusip_lookup.py    # CUSIP → ticker resolution
  scripts/
    setup_db.py          # Entry point: populate database from SEC EDGAR
    resolve_cusips.py    # Entry point: resolve CUSIPs to tickers
    validate_data.py     # Entry point: sanity-check database contents
  tests/
    test_api.py          # API route tests (pytest + TestClient)

frontend/
  src/
    App.jsx              # Route shell, context providers
    pages/               # InstitutionsPage, ConsensusPage, StocksPage
    components/          # layout/, common/, institutions/, heatmap/, charts/, consensus/
    hooks/               # useInstitutions, useTickers, useCardOrder, useDragAndDrop, ...
    api/                 # client.js + per-resource modules
    contexts/            # TickerContext, DrawerContext, HeatmapTooltipContext
    utils/               # formatters, sortUtils, nameUtils, dateUtils
    constants/           # heatmap, chart, sections

Procfile                 # Render: uvicorn backend.app.main:app
vercel.json              # Vercel: static SPA build + rewrites
pyproject.toml           # Python package config (includes backend/)
requirements.txt         # Production Python dependencies
requirements-dev.txt     # Dev/test dependencies (pytest)
```

---

## Tracked Institutions

Berkshire Hathaway · ARK Investment Management · Bridgewater Associates · Soros Fund Management · Pershing Square Capital · Renaissance Technologies · Duquesne Family Office · Tiger Global Management · Third Point · Baupost Group · Lone Pine Capital · H&H International Investment
