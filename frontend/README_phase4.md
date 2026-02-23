# Phase 4 — React Frontend

Single-file React frontend (`index.html`) that consumes the Phase 3 FastAPI backend.
No build step required — uses React 18, Tailwind CSS, and Babel via CDN.

---

## Prerequisites

1. **API must be running** (Phase 3):
   ```bash
   cd /path/to/Smart_Money_Tracker
   python phase3_api.py
   # → http://127.0.0.1:8000
   ```

2. **Serve the frontend** from a local HTTP server.
   Opening `index.html` directly as `file://` can cause CORS issues in some browsers.
   Use Python's built-in server from the `frontend/` directory:
   ```bash
   cd frontend
   python -m http.server 3000
   ```
   Then open: **http://localhost:3000**

---

## File structure

```
frontend/
  index.html       # React app (Tailwind + Babel CDN, all components inline)
  api.js           # All fetch calls — sets window.SmartMoneyAPI
  README_phase4.md # This file
```

---

## What renders

### Page header
- App title ("Smart Money Tracker") and subtitle.

### Global search bar
- Full-width search input at the top.
- Debounced 300 ms — fires once the user pauses typing (min 2 chars).
- Results appear in a dropdown below the bar:
  - Each row: **Issuer name** + CUSIP tag · **Institution** · **Quarter** · **Value** · **Shares**
  - Scrollable up to 30 results.
  - "×" button clears the query and closes the dropdown.
- Closes automatically on outside click.

### Institution cards (2-column grid, stacks to 1 on mobile)

Each card has three areas:

#### 1. Card header
- Institution name (bold) + CIK code.
- Filing date of the currently selected quarter.
- **Quarter selector** dropdown (e.g. "Q4 2025", "Q3 2025", "Q2 2025").

#### 2. Changes section (main body)
Loaded from `GET /changes?period=…` for the selected quarter.

- **Summary bar** — compact inline summary, e.g.:
  ```
  Q3 2025 → Q4 2025  |  +4 new  ↑4  ↓9  ×3 closed
  ```
  Color-coded: emerald for new, green for increased, red for decreased, rose for closed.

- **Four change-type sections**, each with a colored dot + count badge:

  | Section | Color | Shows |
  |---|---|---|
  | New Positions | Emerald | Issuer, CUSIP, shares, current value |
  | Increased | Green | Issuer, CUSIP, prev→curr shares, **% change**, current value |
  | Decreased | Red | Issuer, CUSIP, prev→curr shares, **% change** (red), current value |
  | Closed | Rose | Issuer, CUSIP, final shares held, last-known value |

  ARK typically has 100+ moves per quarter — sections with more than 5 rows show
  **"Show N more ↓"** and collapse back with **"Show less ↑"**.

  Selecting the oldest quarter shows a gentle italic message instead of changes
  (no prior quarter to compare against).

- **Changing the quarter** in the dropdown reloads changes immediately (loading spinner
  shown while fetching, previous data cleared).

#### 3. Full Holdings (collapsible, bottom of card)
Toggled by clicking the **"› Full Holdings"** row.

- Lazy-loads on first expand via `GET /holdings?period=…`.
- Shows: positions count + total portfolio value in the subtitle.
- Table columns: `#` rank · Issuer name (+ CUSIP) · Shares · Value (USD).
- Sorted by value descending (largest position = rank 1).
- Switches to new data automatically when the quarter changes while the section is open.

---

## Behavior notes

- All API calls cancel in-flight if the quarter changes mid-request (no stale overwrites).
- Loading states are shown per-section (not a full-page spinner).
- Error messages are displayed inline where the data would appear.
- If the API is unreachable, a red banner appears at the top of the page.
- Values use compact notation: `$62.0B`, `$640.5M`, `$17.4M`, `$254K`.
- Shares use compact notation: `227.9M`, `3.6M`, `151.6K`.
- Percentage changes always show sign: `+12.3%`, `-77.2%`.
