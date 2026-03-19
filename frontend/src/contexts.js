import { createContext } from 'react';

// Ticker context: Map<cusip, ticker> | null (null = not yet loaded)
export const TickerCtx = createContext(null);

// Drawer context: (cusip: string, issuerName: string) => void
export const StockDrawerCtx = createContext(null);
