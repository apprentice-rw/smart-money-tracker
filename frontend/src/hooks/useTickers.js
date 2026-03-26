import { useState, useEffect } from 'react';
import * as API from '../api/index.js';

export function useTickers() {
  const [tickerMap, setTickerMap] = useState(null);

  useEffect(() => {
    API.getTickers()
      .then((d) => {
        const map = new Map();
        for (const [cusip, entry] of Object.entries(d.tickers)) {
          if (cusip && entry) map.set(cusip, entry);
        }
        setTickerMap(map);
      })
      .catch(() => {}); // silently fail — tickers are best-effort
  }, []);

  return { tickerMap };
}
