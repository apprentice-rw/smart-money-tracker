import { req } from './client.js';

export const getConsensusQuarters = () =>
  req('/consensus/quarters');

export const getConsensusHoldings = (period, minHolders = 2, limit = 50) =>
  req(`/consensus/holdings?period=${encodeURIComponent(period)}&min_holders=${minHolders}&limit=${limit}`);

export const getConsensusBuying = (period, minBuyers = 2, limit = 50) =>
  req(`/consensus/buying?period=${encodeURIComponent(period)}&min_buyers=${minBuyers}&limit=${limit}`);

export const getConsensusSelling = (period, minSellers = 2, limit = 50) =>
  req(`/consensus/selling?period=${encodeURIComponent(period)}&min_sellers=${minSellers}&limit=${limit}`);

export const getConsensusEmerging = (period, limit = 50) =>
  req(`/consensus/emerging?period=${encodeURIComponent(period)}&limit=${limit}`);

export const getConsensusPersistent = (minQuarters = 4, minHolders = 2, limit = 50) =>
  req(`/consensus/persistent?min_quarters=${minQuarters}&min_holders=${minHolders}&limit=${limit}`);
