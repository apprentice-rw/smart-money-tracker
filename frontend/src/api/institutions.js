import { req } from './client.js';

export const getInstitutions = () =>
  req('/institutions');

export const getFilings = (id) =>
  req(`/institutions/${id}/filings`);

export const getHoldings = (id, period) =>
  req(`/institutions/${id}/holdings?period=${encodeURIComponent(period)}`);

export const getChanges = (id, period) =>
  req(`/institutions/${id}/changes?period=${encodeURIComponent(period)}`);
