# Phase 3 — FastAPI Backend

Serves `smart_money.db` (built by `phase2_setup_db.py`) as a REST API.

## Prerequisites

```bash
pip install "fastapi[standard]"
# Phase 2 DB must exist:
python phase2_setup_db.py
```

## Run the server

```bash
# Dev mode (auto-reload on file changes)
python phase3_api.py

# Or directly via uvicorn
uvicorn phase3_api:app --host 127.0.0.1 --port 8000 --reload
```

API is available at `http://127.0.0.1:8000`
Interactive docs (Swagger UI): `http://127.0.0.1:8000/docs`
OpenAPI schema: `http://127.0.0.1:8000/openapi.json`

---

## Endpoints & sample curl commands

### `GET /health`
Returns DB row counts. Use to confirm the API is running and the DB is populated.

```bash
curl http://127.0.0.1:8000/health
```
```json
{
  "status": "ok",
  "database": "/path/to/smart_money.db",
  "row_counts": {
    "institutions": 2,
    "filings": 6,
    "holdings": 707,
    "position_changes": 497
  }
}
```

---

### `GET /institutions`
List all tracked institutions.

```bash
curl http://127.0.0.1:8000/institutions
```
```json
{
  "institutions": [
    { "id": 2, "cik": "0001697748", "name": "ARK Investment Management", "display_name": "ARK Investment Management" },
    { "id": 1, "cik": "0001067983", "name": "Berkshire Hathaway", "display_name": "Berkshire Hathaway" }
  ]
}
```

---

### `GET /institutions/{id}/filings`
List available quarters for an institution, newest first.

```bash
curl http://127.0.0.1:8000/institutions/1/filings
```
```json
{
  "institution": { "id": 1, "cik": "0001067983", "name": "Berkshire Hathaway", ... },
  "filings": [
    { "id": 3, "period_of_report": "2025-12-31", "filing_date": "2026-02-17", "accession_number": "..." },
    { "id": 2, "period_of_report": "2025-09-30", "filing_date": "2025-11-14", "accession_number": "..." },
    { "id": 1, "period_of_report": "2025-06-30", "filing_date": "2025-08-14", "accession_number": "..." }
  ]
}
```

---

### `GET /institutions/{id}/holdings`
Return all holdings for a quarter, sorted by value descending.

| Query param | Default | Description |
|---|---|---|
| `period` | most recent | Quarter end date `YYYY-MM-DD` |

```bash
# Most recent quarter (default)
curl "http://127.0.0.1:8000/institutions/1/holdings"

# Specific quarter
curl "http://127.0.0.1:8000/institutions/2/holdings?period=2025-09-30"
```
```json
{
  "institution": { "id": 1, "name": "Berkshire Hathaway", ... },
  "period_of_report": "2025-12-31",
  "filing_date": "2026-02-17",
  "total_positions": 42,
  "total_value": 274160086701,
  "holdings": [
    { "rank": 1, "cusip": "037833100", "issuer_name": "APPLE INC", "shares": 227917808, "value": 61961735283, "share_type": "SH" },
    { "rank": 2, "cusip": "025816109", "issuer_name": "AMERICAN EXPRESS CO", "shares": 151610700, "value": 56088378465, "share_type": "SH" }
  ]
}
```

> **Note:** `value` is raw USD as filed with the SEC.

---

### `GET /institutions/{id}/changes`
Return precomputed quarter-over-quarter position changes, grouped by type.

| Query param | Default | Description |
|---|---|---|
| `period` | most recent | The *current* (newer) quarter `YYYY-MM-DD` |
| `include_unchanged` | `false` | Also return unchanged positions |

```bash
# Most recent quarter comparison
curl "http://127.0.0.1:8000/institutions/1/changes"

# Specific quarter comparison
curl "http://127.0.0.1:8000/institutions/2/changes?period=2025-09-30"

# Include unchanged positions
curl "http://127.0.0.1:8000/institutions/1/changes?include_unchanged=true"
```
```json
{
  "institution": { "id": 1, "name": "Berkshire Hathaway", ... },
  "prev_period": "2025-09-30",
  "curr_period": "2025-12-31",
  "summary": { "new": 4, "closed": 3, "increased": 4, "decreased": 9, "unchanged": 25 },
  "changes": {
    "new": [
      { "cusip": "530909308", "issuer_name": "LIBERTY LIVE HOLDINGS INC", "change_type": "new",
        "prev_shares": null, "curr_shares": 10917661, "prev_value": null, "curr_value": 907912688, ... }
    ],
    "closed": [ ... ],
    "increased": [
      { "cusip": "25754A201", "issuer_name": "DOMINOS PIZZA INC", "change_type": "increased",
        "prev_shares": 2981945, "curr_shares": 3350000, "shares_delta": 368055, "shares_pct": 12.3428, ... }
    ],
    "decreased": [ ... ]
  }
}
```

> **404** is returned if `period` is the oldest filing in the DB (no prior quarter to compare against).

---

### `GET /search`
Search holdings across all institutions and quarters by issuer name or CUSIP.

| Query param | Default | Description |
|---|---|---|
| `q` | *(required, min 2 chars)* | Name (partial, case-insensitive) or CUSIP (prefix) |
| `limit` | `50` | Max results (1–500) |

```bash
# Search by name
curl "http://127.0.0.1:8000/search?q=apple"

# Search by CUSIP
curl "http://127.0.0.1:8000/search?q=88160R101"

# Search with higher limit
curl "http://127.0.0.1:8000/search?q=tesla&limit=10"
```
```json
{
  "query": "apple",
  "result_count": 3,
  "results": [
    { "cusip": "037833100", "issuer_name": "APPLE INC", "shares": 227917808, "value": 61961735283,
      "share_type": "SH", "period_of_report": "2025-12-31", "institution_id": 1, "institution_name": "Berkshire Hathaway" },
    ...
  ]
}
```

---

## Error responses

All errors use standard HTTP status codes with a JSON body:

```json
{ "detail": "Institution 99 not found." }
```

| Code | When |
|---|---|
| `404` | Institution, period, or changes not found |
| `422` | Invalid query parameter (e.g. `period` format, `q` too short) |
| `503` | `smart_money.db` missing — run `phase2_setup_db.py` first |
