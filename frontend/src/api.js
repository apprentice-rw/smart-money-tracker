/* api.js — all SEC 13F API calls for Smart Money Tracker
 * ES module. BASE is baked in by Vite from VITE_API_URL env var.
 * In local dev (unset), Vite's proxy routes requests to FastAPI on port 8000.
 */

const BASE = import.meta.env.VITE_API_URL ?? '';

async function req(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const getInstitutions = () =>
  req('/institutions');

export const getFilings = (id) =>
  req(`/institutions/${id}/filings`);

export const getHoldings = (id, period) =>
  req(`/institutions/${id}/holdings?period=${encodeURIComponent(period)}`);

export const getChanges = (id, period) =>
  req(`/institutions/${id}/changes?period=${encodeURIComponent(period)}`);

export const search = (q, limit = 50) =>
  req(`/search?q=${encodeURIComponent(q.trim())}&limit=${limit}`);

export const getTickers = () =>
  req('/tickers');
