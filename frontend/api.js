/* api.js — all SEC 13F API calls for Smart Money Tracker
 * Plain JS (no JSX). Sets window.SmartMoneyAPI for use by the React app.
 */

(function (window) {
  'use strict';

  // BASE is set by config.js (injected at Vercel build time).
  // Empty string = relative URLs (FastAPI serves /app locally).
  const BASE = window.__API_BASE__ || '';

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

  window.SmartMoneyAPI = {
    /** GET /institutions */
    getInstitutions: () =>
      req('/institutions'),

    /** GET /institutions/{id}/filings */
    getFilings: (id) =>
      req(`/institutions/${id}/filings`),

    /** GET /institutions/{id}/holdings?period=YYYY-MM-DD */
    getHoldings: (id, period) =>
      req(`/institutions/${id}/holdings?period=${encodeURIComponent(period)}`),

    /** GET /institutions/{id}/changes?period=YYYY-MM-DD */
    getChanges: (id, period) =>
      req(`/institutions/${id}/changes?period=${encodeURIComponent(period)}`),

    /** GET /search?q=...&limit=N */
    search: (q, limit = 50) =>
      req(`/search?q=${encodeURIComponent(q.trim())}&limit=${limit}`),

    /** GET /tickers — name→ticker map proxied from SEC */
    getTickers: () => req('/tickers'),
  };

})(window);
