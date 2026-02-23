// config.js — API base URL injected at Vercel build time.
// In local dev (FastAPI serves /app), this stays empty (relative URLs).
// Vercel buildCommand overwrites this line with the Railway backend URL.
window.__API_BASE__ = '';
