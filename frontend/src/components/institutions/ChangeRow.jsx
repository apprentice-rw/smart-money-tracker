import { useContext } from 'react';
import { TickerCtx } from '../../contexts/TickerContext.js';
import { StockDrawerCtx } from '../../contexts/DrawerContext.js';
import { fmtVal, fmtPct, fmtPrice, fmtShares } from '../../utils/formatters.js';
import { InfoTooltip, QEND_PRICE_TIP } from '../common/InfoTooltip.jsx';

export default function ChangeRow({ item, type, sortKey }) {
  const tickerMap  = useContext(TickerCtx);
  const openDrawer = useContext(StockDrawerCtx);
  const ticker = tickerMap ? tickerMap.get(item.cusip)?.ticker : null;

  const isNew      = type === 'new';
  const isClosed   = type === 'closed';
  const isChanged  = type === 'increased' || type === 'decreased';
  const isPositive = isNew || type === 'increased';

  const currValue  = item.curr_value  || 0;
  const prevValue  = item.prev_value  || 0;
  const currShares = item.curr_shares || 0;
  const prevShares = item.prev_shares || 0;

  const sortByShares = sortKey === 'shares_desc' || sortKey === 'shares_asc';
  const sortByPct    = sortKey === 'pct_desc'    || sortKey === 'pct_asc';
  const prefix       = isPositive ? '+' : '-';
  const headlineColor = isPositive ? 'text-green-600' : 'text-red-500';

  // ── Primary headline: depends on sort + type ──────────────────
  let headline;
  if (isNew) {
    // New: full position value or shares acquired
    headline = (sortByShares || sortByPct)
      ? `+${fmtShares(currShares)} sh`
      : `+${fmtVal(currValue)}`;
  } else if (isClosed) {
    // Closed: last-known value or share count
    headline = (sortByShares || sortByPct)
      ? `-${fmtShares(prevShares)} sh`
      : `-${fmtVal(prevValue)}`;
  } else {
    // Increased / Decreased: delta value, delta shares, or % change
    const deltaShares = currShares - prevShares;            // +ve for increased
    const qEndPrice   = currShares > 0 ? currValue / currShares : 0;
    const deltaValue  = Math.abs(deltaShares * qEndPrice);  // always +ve, sign via prefix
    if (sortByPct) {
      headline = fmtPct(item.shares_pct);                   // fmtPct already adds sign
    } else if (sortByShares) {
      headline = `${prefix}${fmtShares(Math.abs(deltaShares))} sh`;
    } else {
      headline = `${prefix}${fmtVal(deltaValue)}`;
    }
  }

  // ── Secondary: % change for increased / decreased ─────────────
  // Hidden when sort is already %, to avoid showing the same number twice.
  const showSecondaryPct = isChanged && !sortByPct && item.shares_pct != null;

  // ── Q-end price for the /sh reference line ────────────────────
  const qEndVal = isClosed ? prevValue : currValue;
  const qEndSh  = isClosed ? prevShares : currShares;

  return (
    <div
      className="py-2.5 border-b border-gray-50 last:border-0 hover:bg-gray-50/60 -mx-5 px-5 transition-colors cursor-pointer"
      onClick={() => openDrawer?.(item.cusip, item.issuer_name)}
    >
      <div className="flex items-start justify-between gap-3">
        {/* Left: name + ticker + CUSIP */}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-gray-900 leading-snug">
            {item.issuer_name}
            {ticker && <span className="ml-1.5 text-[11px] text-gray-400 font-normal">{ticker}</span>}
          </p>
          <code className="block text-[11px] text-gray-400 tracking-wide">{item.cusip}</code>
        </div>

        {/* Right: headline + secondary % + Q-end price */}
        <div className="text-right flex-shrink-0" style={{ fontVariantNumeric: 'tabular-nums' }}>
          <div className={`text-sm font-semibold ${headlineColor}`}>{headline}</div>
          {showSecondaryPct && (
            <div className="text-[11px] text-gray-400">{fmtPct(item.shares_pct)}</div>
          )}
          <div className="text-[11px] text-gray-400 flex items-center justify-end gap-0.5">
            {fmtPrice(qEndVal, qEndSh)}/sh
            <InfoTooltip text={QEND_PRICE_TIP} />
          </div>
        </div>
      </div>

      {/* Shares arrow context line for increased / decreased */}
      {isChanged && (
        <div className="mt-0.5 text-[11px] text-gray-400" style={{ fontVariantNumeric: 'tabular-nums' }}>
          {fmtShares(prevShares)} → {fmtShares(currShares)} shares
        </div>
      )}
    </div>
  );
}
