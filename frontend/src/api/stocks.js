import { req } from './client.js';

export const search = (q, limit = 50) =>
  req(`/search?q=${encodeURIComponent(q.trim())}&limit=${limit}`);

export const getTickers = () =>
  req('/tickers');

export const getStockHistory = (cusip) =>
  req(`/stock/${encodeURIComponent(cusip)}/history`);
