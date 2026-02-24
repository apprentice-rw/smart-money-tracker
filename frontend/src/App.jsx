import React, { useState, useEffect, useRef, useMemo, createContext, useContext } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { createPortal } from 'react-dom';
import * as API from './api.js';

// ── Utilities ────────────────────────────────────────────────────

function fmtVal(v) {
  if (v == null) return '—';
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v}`;
}

function fmtShares(n) {
  if (n == null) return '—';
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return `${n}`;
}

function fmtPct(p) {
  if (p == null) return '';
  return `${p >= 0 ? '+' : ''}${p.toFixed(1)}%`;
}

function fmtPeriod(s) {
  if (!s) return '';
  const [year, month] = s.split('-');
  return `Q${Math.ceil(parseInt(month, 10) / 3)} ${year}`;
}

function fmtPrice(value, shares) {
  if (!value || !shares || shares === 0) return '—';
  return `$${(value / shares).toFixed(2)}`;
}

// Sort change-group items by the selected key.
// Uses useMemo at call sites — must not mutate the original array.
function sortItems(items, sortKey, type) {
  if (!items || items.length === 0) return items;
  const getValue  = (it) => (type === 'closed' ? it.prev_value  : it.curr_value)  || 0;
  const getShares = (it) => (type === 'closed' ? it.prev_shares : it.curr_shares) || 0;
  const arr = [...items];
  switch (sortKey) {
    case 'value_asc':   return arr.sort((a, b) => getValue(a)        - getValue(b));
    case 'pct_desc':    return arr.sort((a, b) => (b.shares_pct||0) - (a.shares_pct||0));
    case 'pct_asc':     return arr.sort((a, b) => (a.shares_pct||0) - (b.shares_pct||0));
    case 'shares_desc': return arr.sort((a, b) => getShares(b)      - getShares(a));
    case 'shares_asc':  return arr.sort((a, b) => getShares(a)      - getShares(b));
    default:            return arr.sort((a, b) => getValue(b)        - getValue(a)); // value_desc
  }
}

// Ticker context: Map<cusip, ticker> | null (null = not yet loaded)
const TickerCtx = createContext(null);

// Drawer context: (cusip: string, issuerName: string) => void
const StockDrawerCtx = createContext(null);

// ── Shared primitives ─────────────────────────────────────────────

function Spinner({ small = false }) {
  const sz = small ? 'w-4 h-4' : 'w-7 h-7';
  return (
    <div className="flex justify-center py-4">
      <div className={`${sz} border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin`} />
    </div>
  );
}

// ── Info tooltip ──────────────────────────────────────────────────

const QEND_PRICE_TIP =
  "This is the stock\u2019s market price at quarter-end, not the institution\u2019s " +
  "actual cost basis. True cost basis cannot be determined from 13F filings alone.";

function InfoTooltip({ text }) {
  return (
    <span className="relative group inline-flex items-center ml-0.5">
      <span className="text-gray-300 hover:text-gray-500 cursor-help select-none text-[10px]"
            onClick={(e) => e.stopPropagation()}>ⓘ</span>
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2
                       w-52 px-2.5 py-2 rounded-lg bg-gray-800 text-white text-[11px] leading-snug
                       opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50
                       shadow-xl whitespace-normal text-left">
        {text}
      </span>
    </span>
  );
}

function ChevronIcon({ open }) {
  return (
    <svg
      className={`w-3.5 h-3.5 text-gray-400 flex-shrink-0 chevron ${open ? 'open' : ''}`}
      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}

// ── Section header with colored dot + count badge ─────────────────

const SECTION_STYLES = {
  new:       { dot: 'bg-emerald-500', badge: 'bg-emerald-100 text-emerald-700' },
  increased: { dot: 'bg-green-500',   badge: 'bg-green-100  text-green-700'   },
  decreased: { dot: 'bg-red-400',     badge: 'bg-red-100    text-red-600'     },
  closed:    { dot: 'bg-rose-500',    badge: 'bg-rose-100   text-rose-700'    },
};

function SectionHeader({ type, label, count }) {
  const s = SECTION_STYLES[type] || SECTION_STYLES.new;
  return (
    <div className="flex items-center gap-2 mt-6 mb-2">
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.dot}`} />
      <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</span>
      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${s.badge}`}>{count}</span>
    </div>
  );
}

// ── Single position-change row ─────────────────────────────────────

function ChangeRow({ item, type, sortKey }) {
  const tickerMap  = useContext(TickerCtx);
  const openDrawer = useContext(StockDrawerCtx);
  const ticker = tickerMap ? tickerMap.get(item.cusip) : null;

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

// ── Section: group of changes (new / increased / decreased / closed) ──

const DEFAULT_VISIBLE = 3;

function ChangeGroup({ items, type, label, sortKey }) {
  const [showAll, setShowAll] = useState(false);

  // Reset "show more" whenever sort order changes
  useEffect(() => { setShowAll(false); }, [sortKey]);

  // Memoised sort — only recomputes when items, sortKey, or type change.
  // Safe for large datasets (e.g. RenTech's 1 600+ decreased rows).
  const sorted = useMemo(() => sortItems(items, sortKey, type), [items, sortKey, type]);

  if (!items || items.length === 0) return null;

  const visible    = showAll ? sorted : sorted.slice(0, DEFAULT_VISIBLE);
  const hiddenCount = items.length - DEFAULT_VISIBLE;

  return (
    <div>
      <SectionHeader type={type} label={label} count={items.length} />
      <div>
        {visible.map((item) => (
          <ChangeRow key={`${item.cusip}-${type}`} item={item} type={type} sortKey={sortKey} />
        ))}
      </div>
      {!showAll && hiddenCount > 0 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-1.5 text-xs text-blue-600 hover:text-blue-700 font-medium"
        >
          Show {hiddenCount} more ↓
        </button>
      )}
      {showAll && items.length > DEFAULT_VISIBLE && (
        <button
          onClick={() => setShowAll(false)}
          className="mt-1.5 text-xs text-gray-400 hover:text-gray-600 font-medium"
        >
          Show less ↑
        </button>
      )}
    </div>
  );
}

// ── Full-holdings table (receives data from parent, lazy open) ────

function HoldingsSection({ data, loading, error }) {
  const tickerMap  = useContext(TickerCtx);
  const openDrawer = useContext(StockDrawerCtx);
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-5 pt-4 border-t border-gray-100">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800 font-medium transition-colors"
      >
        <ChevronIcon open={open} />
        <span>Full Holdings</span>
        {data && (
          <span className="text-xs text-gray-400 font-normal">
            {data.total_positions} positions · {fmtVal(data.total_value)}
          </span>
        )}
      </button>

      {open && (
        <div className="mt-3">
          {loading && <Spinner small />}
          {error && <p className="text-sm text-red-400 py-2">{error}</p>}
          {data && !loading && (
            <>
              <p className="text-xs text-gray-400 mb-3" style={{ fontVariantNumeric: 'tabular-nums' }}>
                {data.total_positions} positions · {fmtVal(data.total_value)} total value · {fmtPeriod(data.period_of_report)}
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="pb-2 pr-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right w-7">#</th>
                      <th className="pb-2 pr-4 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Issuer</th>
                      <th className="pb-2 pr-4 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right">Shares</th>
                      <th className="pb-2 pr-4 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right">Weight</th>
                      <th className="pb-2 pr-4 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right">
                        <span className="inline-flex items-center justify-end gap-0.5">
                          Q-end Price <InfoTooltip text={QEND_PRICE_TIP} />
                        </span>
                      </th>
                      <th className="pb-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.holdings.map((h) => {
                      const ticker = tickerMap ? tickerMap.get(h.cusip) : null;
                      const weight = data.total_value > 0
                        ? (h.value / data.total_value * 100).toFixed(1) + '%'
                        : '—';
                      return (
                        <tr
                          key={h.cusip}
                          className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors cursor-pointer"
                          onClick={() => openDrawer?.(h.cusip, h.issuer_name)}
                        >
                          <td className="py-2 pr-2 text-xs text-gray-400 text-right"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{h.rank}</td>
                          <td className="py-2 pr-4">
                            <span className="text-sm text-gray-900">{h.issuer_name}</span>
                            {ticker && <span className="ml-1.5 text-[11px] text-gray-400">{ticker}</span>}
                            <code className="ml-2 text-[11px] text-gray-400 hidden sm:inline">{h.cusip}</code>
                          </td>
                          <td className="py-2 pr-4 text-sm text-right text-gray-600"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtShares(h.shares)}</td>
                          <td className="py-2 pr-4 text-sm text-right text-gray-500"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{weight}</td>
                          <td className="py-2 pr-4 text-sm text-right text-gray-500"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(h.value, h.shares)}</td>
                          <td className="py-2 text-sm text-right font-semibold text-gray-800"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtVal(h.value)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Error boundary for institution cards ──────────────────────────

class CardErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('InstitutionCard render error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-white border border-red-100 rounded-2xl shadow-sm p-5">
          <p className="text-sm font-semibold text-red-400 mb-1">Failed to render card</p>
          <p className="text-xs text-gray-400">{this.state.error?.message}</p>
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Stats bar: positions · turnover · top-5 concentration ─────────

function StatsBar({ changes, holdingsData }) {
  if (!changes) return null;
  const { summary } = changes;

  // Total current positions = everything except closed
  const totalPositions = (summary.new || 0) + (summary.increased || 0)
                       + (summary.decreased || 0) + (summary.unchanged || 0);

  // Turnover = (new + closed) / total current positions
  const turnover = totalPositions > 0
    ? (((summary.new || 0) + (summary.closed || 0)) / totalPositions * 100).toFixed(1)
    : '—';

  // Top-5 concentration from eagerly-loaded holdings
  let top5Pct = null;
  if (holdingsData && holdingsData.total_value > 0) {
    const top5Val = holdingsData.holdings
      .slice(0, 5)
      .reduce((s, h) => s + (h.value || 0), 0);
    top5Pct = (top5Val / holdingsData.total_value * 100).toFixed(1);
  }

  return (
    <div className="flex items-center gap-2.5 mt-1.5 flex-wrap"
         style={{ fontVariantNumeric: 'tabular-nums' }}>
      <span className="text-[11px] text-gray-400">
        <span className="font-semibold text-gray-600">{totalPositions}</span> pos
      </span>
      <span className="text-gray-200 text-[10px]">·</span>
      <span className="text-[11px] text-gray-400">
        <span className="font-semibold text-gray-600">{turnover}%</span> turnover
      </span>
      <span className="text-gray-200 text-[10px]">·</span>
      <span className="text-[11px] text-gray-400">
        {top5Pct !== null
          ? <><span className="font-semibold text-gray-600">{top5Pct}%</span> top-5</>
          : <span className="text-gray-300">top-5 …</span>}
      </span>
    </div>
  );
}

// ── Stock history drawer ──────────────────────────────────────────

const CHART_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4', '#f97316'];

function ChartTooltip({ active, payload, label, mode }) {
  if (!active || !payload?.length) return null;
  const visible = payload.filter((p) => p.value != null);
  if (!visible.length) return null;
  return (
    <div className="bg-white border border-gray-100 rounded-xl shadow-lg px-3 py-2.5 text-xs">
      <p className="font-semibold text-gray-700 mb-1">{fmtPeriod(label)}</p>
      {visible.map((p) => {
        const isClosed = p.value === 0;
        return (
          <div key={p.dataKey} className="flex items-center gap-2 py-0.5">
            <span className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: isClosed ? '#ef4444' : p.color }} />
            <span className="text-gray-600">{p.name}:</span>
            <span className={`font-semibold ${isClosed ? 'text-red-500' : 'text-gray-900'}`}>
              {isClosed
                ? 'Closed'
                : mode === 'value'
                  ? fmtVal(p.value)
                  : p.value.toFixed(2) + '%'}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ChartLegend({ payload }) {
  if (!payload?.length) return null;
  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: '8px 20px',
      justifyContent: 'center',
      marginTop: 10,
      padding: '0 8px',
    }}>
      {payload.map((entry) => (
        <div key={entry.value} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width={8} height={8} style={{ flexShrink: 0 }}>
            <circle cx={4} cy={4} r={4} fill={entry.color} />
          </svg>
          <span style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.4 }}>{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

function StockHistoryDrawer({ cusip, issuerName, onClose }) {
  const tickerMap               = useContext(TickerCtx);
  const [data, setData]         = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [mode, setMode]         = useState('value'); // 'value' | 'weight'
  const [enabledInsts, setEnabledInsts] = useState(new Set());

  // Fetch history on mount; initialise all institutions as enabled
  useEffect(() => {
    setLoading(true); setError(null);
    API.getStockHistory(cusip)
      .then((d) => {
        setData(d);
        setLoading(false);
        setEnabledInsts(new Set(d.history.map((r) => r.institution_id)));
      })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [cusip]);

  function toggleInst(id) {
    setEnabledInsts((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  }

  // Escape key closes
  useEffect(() => {
    const fn = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', fn);
    return () => document.removeEventListener('keydown', fn);
  }, [onClose]);

  // Lock body scroll while open
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  // Build Recharts data: one entry per period, one key per institution.
  // Also computes openPoints / closedPoints for custom dot rendering.
  const { chartData, institutions, openPoints, closedPoints } = useMemo(() => {
    if (!data) return { chartData: [], institutions: [], openPoints: new Set(), closedPoints: new Set() };
    const history = data.history;
    const periods = [...new Set(history.map((r) => r.period_of_report))].sort();
    const insts = [...new Map(
      history.map((r) => [r.institution_id, { id: r.institution_id, name: r.institution_name }])
    ).values()];

    const openPoints   = new Set(); // "period::instId"
    const closedPoints = new Set(); // "period::instId"

    // Base data: one entry per period
    const cd = periods.map((period) => {
      const entry = { period };
      for (const inst of insts) {
        const row = history.find(
          (r) => r.period_of_report === period && r.institution_id === inst.id
        );
        if (row) {
          entry[`v_${inst.id}`] = mode === 'value'
            ? row.value
            : (row.portfolio_weight ?? 0) * 100;
        }
        // No entry = gap (connectNulls={false})
      }
      return entry;
    });

    // Detect first/last held quarter per institution
    for (const inst of insts) {
      const held = periods.filter((p) =>
        history.some((r) => r.period_of_report === p && r.institution_id === inst.id)
      );
      if (!held.length) continue;

      openPoints.add(`${held[0]}::${inst.id}`);

      // If not held through the final period, add a zero drop at the next period
      const lastIdx = periods.indexOf(held[held.length - 1]);
      if (lastIdx < periods.length - 1) {
        const dropPeriod = periods[lastIdx + 1];
        cd[lastIdx + 1][`v_${inst.id}`] = 0;
        closedPoints.add(`${dropPeriod}::${inst.id}`);
      }
    }

    return { chartData: cd, institutions: insts, openPoints, closedPoints };
  }, [data, mode]);

  // Compute 5-pointed star polygon points centered at (cx, cy)
  function starPts(cx, cy, outerR, innerR) {
    const pts = [];
    for (let i = 0; i < 10; i++) {
      const angle = (i * Math.PI) / 5 - Math.PI / 2;
      const r = i % 2 === 0 ? outerR : innerR;
      pts.push(`${(cx + r * Math.cos(angle)).toFixed(2)},${(cy + r * Math.sin(angle)).toFixed(2)}`);
    }
    return pts.join(' ');
  }

  // Custom dot renderer: star = new position, X = closed, circle = normal
  const renderDot = (inst, instIdx) => (props) => {
    const { cx, cy, payload, value } = props;
    if (cx == null || cy == null || value == null) return null;
    const key   = `${payload.period}::${inst.id}`;
    const color = CHART_COLORS[instIdx % CHART_COLORS.length];

    if (closedPoints.has(key)) {
      const s = 5;
      return (
        <g key={key}>
          <line x1={cx - s} y1={cy - s} x2={cx + s} y2={cy + s}
                stroke="#ef4444" strokeWidth={2.5} strokeLinecap="round" />
          <line x1={cx + s} y1={cy - s} x2={cx - s} y2={cy + s}
                stroke="#ef4444" strokeWidth={2.5} strokeLinecap="round" />
        </g>
      );
    }
    if (openPoints.has(key)) {
      return (
        <polygon
          key={key}
          points={starPts(cx, cy, 7, 3)}
          fill={color} stroke="white" strokeWidth={1}
        />
      );
    }
    return <circle key={key} cx={cx} cy={cy} r={3} fill={color} stroke="none" />;
  };

  const ticker = tickerMap?.get(cusip);

  return createPortal(
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/30 backdrop-blur-sm cursor-pointer" onClick={onClose} />

      {/* Drawer panel */}
      <div className="smt-drawer w-full max-w-xl bg-white shadow-2xl flex flex-col h-full">

        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 flex items-start justify-between gap-3 flex-shrink-0">
          <div className="min-w-0">
            <p className="text-base font-bold leading-snug truncate">
              <span className="text-gray-900">{issuerName}</span>
              {ticker && (
                <span className="ml-2 text-blue-500 font-bold text-sm">{ticker}</span>
              )}
            </p>
            <code className="text-[11px] text-gray-400 tracking-wide">{cusip}</code>
          </div>
          <button
            onClick={onClose}
            className="flex-shrink-0 p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors text-lg leading-none"
          >×</button>
        </div>

        {/* Mode toggle */}
        <div className="px-6 py-3 border-b border-gray-50 flex items-center gap-2 flex-shrink-0">
          {[['value', 'Market Value'], ['weight', 'Portfolio %']].map(([val, label]) => (
            <button
              key={val}
              onClick={() => setMode(val)}
              className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                mode === val
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'text-gray-500 border-gray-200 hover:border-gray-300'
              }`}
            >{label}</button>
          ))}
        </div>

        {/* Institution toggles — only shown when data loaded */}
        {institutions.length > 0 && (
          <div className="px-5 py-2.5 border-b border-gray-50 flex flex-wrap gap-1.5 flex-shrink-0">
            {institutions.map((inst, idx) => {
              const checked = enabledInsts.has(inst.id);
              const color   = CHART_COLORS[idx % CHART_COLORS.length];
              return (
                <button
                  key={inst.id}
                  onClick={() => toggleInst(inst.id)}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border transition-colors ${
                    checked
                      ? 'bg-white border-gray-200 text-gray-700 shadow-sm'
                      : 'bg-gray-50 border-gray-100 text-gray-400'
                  }`}
                >
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0 transition-colors"
                    style={{ background: checked ? color : '#d1d5db' }}
                  />
                  {inst.name}
                </button>
              );
            })}
          </div>
        )}

        {/* Chart */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {loading && <Spinner />}
          {error && <p className="text-sm text-red-400 py-4 text-center">{error}</p>}
          {data && !loading && chartData.length === 0 && (
            <p className="text-sm text-gray-400 py-4 text-center">No history available.</p>
          )}
          {data && !loading && chartData.length > 0 && (
            <>
              <ResponsiveContainer width="100%" height={380}>
                <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="period"
                    tickFormatter={fmtPeriod}
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                  />
                  <YAxis
                    tickFormatter={mode === 'value' ? fmtVal : (v) => v.toFixed(1) + '%'}
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    width={64}
                  />
                  <Tooltip content={<ChartTooltip mode={mode} />} />
                  <Legend content={<ChartLegend />} />
                  {institutions.map((inst, idx) => {
                    if (!enabledInsts.has(inst.id)) return null;
                    return (
                      <Line
                        key={inst.id}
                        type="monotone"
                        dataKey={`v_${inst.id}`}
                        name={inst.name}
                        stroke={CHART_COLORS[idx % CHART_COLORS.length]}
                        strokeWidth={2}
                        dot={renderDot(inst, idx)}
                        activeDot={{ r: 5 }}
                        connectNulls={false}
                      />
                    );
                  })}
                </LineChart>
              </ResponsiveContainer>
              <p className="mt-3 text-center text-[11px] text-gray-300">
                ★ new position &nbsp;·&nbsp; <span className="text-red-300">✕ closed position</span>
              </p>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}

// ── Institution card ──────────────────────────────────────────────

function InstitutionCard({ institution, onAumLoaded, onDragHandleMouseDown, collapsed, onCollapseToggle }) {
  const [filings, setFilings]           = useState([]);
  const [filingsError, setFilingsError] = useState(null);
  const [period, setPeriod]             = useState(null);
  const [changes, setChanges]           = useState(null);
  const [changesLoading, setCLoading]   = useState(false);
  const [changesError, setCError]       = useState(null);

  // Holdings fetched eagerly for stats bar + HoldingsSection (no double-fetch)
  const [holdingsData, setHoldingsData] = useState(null);
  const [holdingsLoading, setHLoading]  = useState(false);
  const [holdingsError, setHError]      = useState(null);

  const [sortKey, setSortKey] = useState('value_desc');

  // Load available quarters
  useEffect(() => {
    API.getFilings(institution.id)
      .then((d) => {
        setFilings(d.filings);
        if (d.filings.length > 0) setPeriod(d.filings[0].period_of_report);
      })
      .catch((e) => setFilingsError(e.message || 'Failed to load quarters'));
  }, [institution.id]);

  // Load changes whenever the selected quarter changes
  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setChanges(null); setCError(null); setCLoading(true);
    API.getChanges(institution.id, period)
      .then((d) => { if (!cancelled) { setChanges(d); setCLoading(false); } })
      .catch((e) => { if (!cancelled) { setCError(e.message); setCLoading(false); } });
    return () => { cancelled = true; };
  }, [institution.id, period]);

  // Eagerly load holdings (same endpoint HoldingsSection used to call lazily)
  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setHoldingsData(null); setHError(null); setHLoading(true);
    API.getHoldings(institution.id, period)
      .then((d) => {
        if (!cancelled) {
          setHoldingsData(d);
          setHLoading(false);
          // Report AUM to App for default sort — only for the most recent filing
          if (onAumLoaded && filings.length > 0 && period === filings[0].period_of_report) {
            onAumLoaded(d.total_value || 0);
          }
        }
      })
      .catch((e) => { if (!cancelled) { setHError(e.message); setHLoading(false); } });
    return () => { cancelled = true; };
  }, [institution.id, period, filings]);

  const currentFiling = filings.find((f) => f.period_of_report === period);

  return (
    <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden flex flex-col">

      {/* ── Card header (always visible) ── */}
      <div className="px-5 pt-5 pb-4 border-b border-gray-50">
        <div className="flex items-start justify-between gap-4">

          {/* Drag handle */}
          <span className="flex-shrink-0 mt-0.5 text-gray-300 hover:text-gray-400
                           cursor-grab select-none text-xl leading-none"
                title="Drag to reorder"
                onMouseDown={onDragHandleMouseDown}>⠿</span>

          {/* Left: name + meta + stats bar */}
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2 flex-wrap">
              <h2 className="text-base font-bold text-gray-900 leading-tight">
                {institution.name}
              </h2>
              {/* AUM shown inline when collapsed */}
              {collapsed && holdingsData && (
                <span className="text-sm font-semibold text-gray-400">
                  {fmtVal(holdingsData.total_value)}
                </span>
              )}
            </div>
            {!collapsed && (
              <div className="flex items-center gap-2 mt-1">
                <code className="text-[11px] text-gray-400">CIK {institution.cik}</code>
                {currentFiling && (
                  <>
                    <span className="text-gray-200">·</span>
                    <span className="text-[11px] text-gray-400">
                      filed {currentFiling.filing_date}
                    </span>
                  </>
                )}
              </div>
            )}
            {/* Stats bar always visible */}
            <StatsBar changes={changes} holdingsData={holdingsData} />
          </div>

          {/* Right: quarter selector + collapse button */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {!collapsed && filings.length > 0 && (
              <select
                value={period || ''}
                onChange={(e) => setPeriod(e.target.value)}
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-700 bg-white
                           focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer
                           hover:border-gray-300 transition-colors"
              >
                {filings.map((f) => (
                  <option key={f.id} value={f.period_of_report}>
                    {fmtPeriod(f.period_of_report)}
                  </option>
                ))}
              </select>
            )}

            {/* Collapse / expand toggle */}
            <button
              onClick={onCollapseToggle}
              title={collapsed ? 'Expand' : 'Collapse'}
              className="p-1 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            >
              <svg
                className={`w-4 h-4 transition-transform duration-200 ${collapsed ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* ── Card body (hidden when collapsed) ── */}
      {!collapsed && (
        <div className="px-5 py-4 overflow-y-auto max-h-[600px] thin-scroll">

          {filingsError && (
            <p className="text-xs text-red-400 py-2 italic">{filingsError}</p>
          )}

          {changesLoading && <Spinner />}

          {changesError && !changesLoading && (
            <p className="text-sm text-gray-400 italic py-2">
              {changesError.toLowerCase().includes('no position changes') || changesError.toLowerCase().includes('oldest')
                ? `No comparison available for ${fmtPeriod(period)} — oldest quarter in the database.`
                : changesError}
            </p>
          )}

          {changes && !changesLoading && (
            <div>
              {/* Quarter-over-quarter summary line */}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-2 text-sm">
                <span className="text-xs text-gray-400">
                  {fmtPeriod(changes.prev_period)} → {fmtPeriod(changes.curr_period)}
                </span>
                <span className="text-gray-200 text-xs">|</span>
                {changes.summary.new > 0 && (
                  <span className="text-emerald-600 font-semibold text-xs">
                    +{changes.summary.new} new
                  </span>
                )}
                {changes.summary.increased > 0 && (
                  <span className="text-green-600 font-semibold text-xs">
                    ↑{changes.summary.increased}
                  </span>
                )}
                {changes.summary.decreased > 0 && (
                  <span className="text-red-500 font-semibold text-xs">
                    ↓{changes.summary.decreased}
                  </span>
                )}
                {changes.summary.closed > 0 && (
                  <span className="text-rose-600 font-semibold text-xs">
                    ×{changes.summary.closed} closed
                  </span>
                )}
                {(changes.summary.unchanged || 0) > 0 && (
                  <span className="text-gray-300 text-xs">
                    {changes.summary.unchanged} unchanged
                  </span>
                )}
              </div>

              {/* Sort control */}
              <div className="flex items-center gap-2 pb-3 mb-1 border-b border-gray-50">
                <span className="text-[11px] text-gray-400">Sort by</span>
                <select
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value)}
                  className="text-[11px] border border-gray-200 rounded px-2 py-1 text-gray-600 bg-white
                             focus:outline-none focus:ring-1 focus:ring-blue-400 cursor-pointer
                             hover:border-gray-300 transition-colors"
                >
                  <option value="value_desc">Value ↓</option>
                  <option value="value_asc">Value ↑</option>
                  <option value="pct_desc">% Change ↓</option>
                  <option value="pct_asc">% Change ↑</option>
                  <option value="shares_desc">Shares ↓</option>
                  <option value="shares_asc">Shares ↑</option>
                </select>
              </div>

              <ChangeGroup items={changes.changes.new}       type="new"       label="New Positions" sortKey={sortKey} />
              <ChangeGroup items={changes.changes.increased} type="increased" label="Increased"      sortKey={sortKey} />
              <ChangeGroup items={changes.changes.decreased} type="decreased" label="Decreased"      sortKey={sortKey} />
              <ChangeGroup items={changes.changes.closed}    type="closed"    label="Closed"         sortKey={sortKey} />
            </div>
          )}

          {/* Full holdings — data passed from parent, no internal fetch */}
          {period && (
            <HoldingsSection
              data={holdingsData}
              loading={holdingsLoading}
              error={holdingsError}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ── Global search (client-side institution filter) ────────────────

function SearchBar({ institutions, cardRefsMap, setHighlightId }) {
  const [query,  setQuery]  = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const inputRef        = useRef(null);
  const panelRef        = useRef(null);
  const highlightTimer  = useRef(null);

  // Clear the highlight timer on unmount to prevent stale state updates.
  useEffect(() => () => clearTimeout(highlightTimer.current), []);

  const filtered = institutions.filter((inst) =>
    inst.name.toLowerCase().includes(query.toLowerCase())
  );

  const showPanel = isOpen && query.length > 0;

  function handleSelect(inst) {
    cardRefsMap.current[inst.id]?.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setHighlightId(inst.id);
    clearTimeout(highlightTimer.current);
    highlightTimer.current = setTimeout(() => setHighlightId(null), 1500);
    setQuery('');
    setIsOpen(false);
  }

  // Outside-click closes the dropdown
  useEffect(() => {
    if (!showPanel) return;
    function onMouseDown(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [showPanel]);

  // Escape closes
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') setIsOpen(false);
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div ref={panelRef} className="relative">
      {/* Input */}
      <div className="relative">
        <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
             fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setIsOpen(true); }}
          placeholder="Search institutions…"
          className="w-full pl-10 pr-9 py-3 border border-gray-200 rounded-xl text-sm text-gray-900
                     bg-white placeholder-gray-400 shadow-sm
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setIsOpen(false); inputRef.current?.focus(); }}
            className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400
                       hover:text-gray-600 text-lg leading-none font-light"
          >
            ×
          </button>
        )}
      </div>

      {/* Institution dropdown */}
      {showPanel && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1.5 bg-white border border-gray-100
                        rounded-xl shadow-lg overflow-hidden max-h-80 overflow-y-auto thin-scroll">
          {filtered.length === 0 ? (
            <p className="px-4 py-3 text-sm text-gray-400">No institutions found</p>
          ) : (
            filtered.map((inst) => (
              <button
                key={inst.id}
                onClick={() => handleSelect(inst)}
                className="w-full text-left px-4 py-2.5 hover:bg-gray-50 border-b border-gray-50
                           last:border-0 transition-colors text-sm font-medium text-gray-900"
              >
                {inst.name}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Root App ──────────────────────────────────────────────────────

function App() {
  const [institutions, setInstitutions] = useState([]);
  const [error, setError]               = useState(null);
  const [tickerMap, setTickerMap]       = useState(null);
  const [highlightId, setHighlightId]   = useState(null);
  const cardRefsMap     = useRef({});
  const orderedInstsRef = useRef([]);
  const ghostRef        = useRef(null);

  // ── Drag-and-drop ordering ─────────────────────────────────────
  // cardOrder: array of institution IDs, or null = use AUM-descending default
  const [cardOrder, setCardOrder] = useState(() => {
    try { return JSON.parse(localStorage.getItem('smt_card_order')) || null; }
    catch { return null; }
  });
  // aumMap: {id: total_value} reported by each card on load, persisted so
  //         the default AUM sort is stable across page refreshes
  const [aumMap, setAumMap] = useState(() => {
    try { return JSON.parse(localStorage.getItem('smt_aum_map')) || {}; }
    catch { return {}; }
  });
  const [draggingId,   setDraggingId]   = useState(null);
  const [dragOverId,   setDragOverId]   = useState(null);
  const [collapsedMap, setCollapsedMap] = useState({});

  // ── Stock history drawer ───────────────────────────────────────
  const [drawerCusip, setDrawerCusip] = useState(null);
  const [drawerName,  setDrawerName]  = useState(null);

  function openStockDrawer(cusip, issuerName) {
    setDrawerCusip(cusip);
    setDrawerName(issuerName || cusip);
  }
  function closeStockDrawer() {
    setDrawerCusip(null);
    setDrawerName(null);
  }

  useEffect(() => {
    API.getInstitutions()
      .then((d) => {
        const insts = d.institutions;
        insts.forEach((inst) => {
          if (!cardRefsMap.current[inst.id]) {
            cardRefsMap.current[inst.id] = { current: null };
          }
        });
        setInstitutions(insts);
      })
      .catch((e) => setError(e.message));
  }, []);

  // Fetch CUSIP→ticker map from our API (populated by cusip_lookup.py)
  useEffect(() => {
    API.getTickers()
      .then((d) => {
        const map = new Map();
        for (const [cusip, ticker] of Object.entries(d.tickers)) {
          if (cusip && ticker) map.set(cusip, ticker);
        }
        setTickerMap(map);
      })
      .catch(() => {}); // silently fail — tickers are best-effort
  }, []);

  // ── AUM callback (from InstitutionCard once holdings load) ─────
  function handleAumLoaded(id, aum) {
    setAumMap((prev) => {
      if (prev[id] === aum) return prev;
      const next = { ...prev, [id]: aum };
      localStorage.setItem('smt_aum_map', JSON.stringify(next));
      return next;
    });
  }

  // ── Mouse-event drag ordering ───────────────────────────────────
  function handleHandleMouseDown(e, instId) {
    if (e.button !== 0) return;
    e.preventDefault();

    document.body.style.cursor     = 'grabbing';
    document.body.style.userSelect = 'none';

    // ── Floating ghost ──────────────────────────────────────────
    const inst  = orderedInstsRef.current.find(i => i.id === instId);
    const ghost = document.createElement('div');
    ghost.className = 'smt-ghost';
    ghost.style.cssText = [
      'position:fixed',
      'pointer-events:none',
      'z-index:9999',
      'background:white',
      'border:1px solid #e5e7eb',
      'border-radius:16px',
      'padding:12px 20px',
      'box-shadow:0 24px 48px rgba(0,0,0,0.18),0 6px 16px rgba(0,0,0,0.10)',
      'min-width:180px',
      'max-width:300px',
      'font-family:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif',
      'left:' + (e.clientX + 16) + 'px',
      'top:'  + (e.clientY + 16) + 'px',
    ].join(';');

    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:8px';
    const hIcon = document.createElement('span');
    hIcon.textContent = '⠿';
    hIcon.style.cssText = 'color:#9ca3af;font-size:18px;flex-shrink:0';
    const hName = document.createElement('span');
    hName.textContent = inst ? inst.name : '';
    hName.style.cssText = 'font-size:14px;font-weight:700;color:#111827;'
      + 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
    row.appendChild(hIcon);
    row.appendChild(hName);
    ghost.appendChild(row);
    if (inst) {
      const sub = document.createElement('div');
      sub.textContent = 'CIK\u00a0' + inst.cik;
      sub.style.cssText = 'font-size:11px;color:#9ca3af;margin-top:3px;padding-left:26px';
      ghost.appendChild(sub);
    }
    document.body.appendChild(ghost);
    ghostRef.current = ghost;

    setDraggingId(instId);

    // ── Mouse tracking ──────────────────────────────────────────
    let lastRawId = null;

    function onMouseMove(ev) {
      ghost.style.left = (ev.clientX + 16) + 'px';
      ghost.style.top  = (ev.clientY + 16) + 'px';

      const el    = document.elementFromPoint(ev.clientX, ev.clientY);
      const card  = el && el.closest('[data-institution-id]');
      const rawId = card ? card.dataset.institutionId : null;
      // Ignore hits on the card being dragged
      const eid   = (rawId !== null && rawId !== String(instId)) ? rawId : null;
      if (eid === lastRawId) return;
      lastRawId = eid;
      const target = eid
        ? orderedInstsRef.current.find(i => String(i.id) === eid)
        : null;
      setDragOverId(target ? target.id : null);
    }

    function onMouseUp(ev) {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup',   onMouseUp);
      ghost.remove();
      ghostRef.current           = null;
      document.body.style.cursor     = '';
      document.body.style.userSelect = '';

      const el    = document.elementFromPoint(ev.clientX, ev.clientY);
      const card  = el && el.closest('[data-institution-id]');
      const rawId = card ? card.dataset.institutionId : null;
      const tgt   = (rawId !== null && rawId !== String(instId))
        ? orderedInstsRef.current.find(i => String(i.id) === rawId)
        : null;

      if (tgt) {
        const ids  = orderedInstsRef.current.map(i => i.id);
        const from = ids.indexOf(instId);
        const to   = ids.indexOf(tgt.id);
        if (from !== -1 && to !== -1) {
          const next = [...ids];
          next.splice(from, 1);
          next.splice(from < to ? to - 1 : to, 0, instId);
          setCardOrder(next);
          localStorage.setItem('smt_card_order', JSON.stringify(next));
        }
      }

      setDraggingId(null);
      setDragOverId(null);
    }

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup',   onMouseUp);
  }

  function resetOrder() {
    setCardOrder(null);
    localStorage.removeItem('smt_card_order');
  }

  // ── Collapse helpers ────────────────────────────────────────────
  function toggleCollapse(id) {
    setCollapsedMap(prev => ({ ...prev, [id]: !prev[id] }));
  }
  function collapseAll() {
    const next = {};
    institutions.forEach(i => { next[i.id] = true; });
    setCollapsedMap(next);
  }
  function expandAll() { setCollapsedMap({}); }
  const allCollapsed = institutions.length > 0
    && institutions.every(i => collapsedMap[i.id]);

  // ── Ordered institution list ───────────────────────────────────
  const orderedInsts = useMemo(() => {
    if (!institutions.length) return [];
    if (!cardOrder) {
      // Default: AUM descending (uses cached aumMap so order is stable)
      return [...institutions].sort((a, b) => (aumMap[b.id] || 0) - (aumMap[a.id] || 0));
    }
    // Custom order from localStorage; any new institution goes to the end
    const orderMap = Object.fromEntries(cardOrder.map((id, i) => [id, i]));
    return [...institutions].sort(
      (a, b) => (orderMap[a.id] ?? 9999) - (orderMap[b.id] ?? 9999)
    );
  }, [institutions, cardOrder, aumMap]);
  orderedInstsRef.current = orderedInsts;  // keep closure ref current

  return (
    <TickerCtx.Provider value={tickerMap}>
      <StockDrawerCtx.Provider value={openStockDrawer}>
      <div className="max-w-7xl mx-auto px-4 py-8">

        {/* Page header */}
        <header className="mb-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
                Smart Money Tracker
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                SEC 13F filings · institutional position changes
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0 mt-1">
              <button
                onClick={allCollapsed ? expandAll : collapseAll}
                className="text-xs text-gray-400 hover:text-gray-700
                           border border-gray-200 hover:border-gray-300 rounded-lg
                           px-3 py-1.5 transition-colors bg-white shadow-sm"
              >
                {allCollapsed ? 'Expand All' : 'Collapse All'}
              </button>
              <button
                onClick={resetOrder}
                title="Restore default order (AUM descending)"
                className="text-xs text-gray-400 hover:text-gray-700
                           border border-gray-200 hover:border-gray-300 rounded-lg
                           px-3 py-1.5 transition-colors bg-white shadow-sm"
              >
                Reset Order
              </button>
            </div>
          </div>
        </header>

        {/* Global search */}
        <div className="mb-8 max-w-2xl">
          <SearchBar institutions={institutions} cardRefsMap={cardRefsMap} setHighlightId={setHighlightId} />
        </div>

        {/* API error */}
        {error && (
          <div className="mb-6 bg-red-50 border border-red-100 rounded-xl px-5 py-4 text-sm text-red-600">
            Could not reach the API — make sure the server is running at{' '}
            <code className="font-mono">http://127.0.0.1:8000</code>.
            <br />
            <span className="text-red-400 text-xs mt-1 block">{error}</span>
          </div>
        )}

        {/* Loading state */}
        {institutions.length === 0 && !error && (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin" />
          </div>
        )}

        {/* Institution cards — 3-col desktop, 2-col tablet, 1-col mobile */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 items-start">
          {orderedInsts.map((inst) => {
            const isDragging = draggingId === inst.id;
            const isTarget   = dragOverId  === inst.id && !isDragging;
            return (
              <React.Fragment key={inst.id}>

                {/* Drop placeholder — animates in before the target card */}
                {isTarget && (
                  <div data-institution-id={inst.id}
                       className="smt-placeholder rounded-2xl border-2 border-dashed
                                  border-blue-300 bg-blue-50/50 min-h-[120px]
                                  flex items-center justify-center
                                  text-xs text-blue-300 select-none">
                    drop here
                  </div>
                )}

                <div
                  ref={cardRefsMap.current[inst.id]}
                  data-institution-id={inst.id}
                  className={[
                    'rounded-2xl transition-all duration-200',
                    highlightId === inst.id ? 'ring-2 ring-blue-400 shadow-lg' : '',
                    isDragging              ? 'opacity-30'                      : '',
                  ].join(' ')}
                  style={{ pointerEvents: isDragging ? 'none' : undefined }}
                >
                  <CardErrorBoundary>
                    <InstitutionCard
                      institution={inst}
                      onAumLoaded={(aum) => handleAumLoaded(inst.id, aum)}
                      onDragHandleMouseDown={(e) => handleHandleMouseDown(e, inst.id)}
                      collapsed={!!collapsedMap[inst.id]}
                      onCollapseToggle={() => toggleCollapse(inst.id)}
                    />
                  </CardErrorBoundary>
                </div>

              </React.Fragment>
            );
          })}
        </div>

        {/* Footer */}
        <footer className="mt-14 text-center text-xs text-gray-300">
          Smart Money Tracker · SEC EDGAR 13F data
        </footer>
      </div>

      {/* Stock history drawer — rendered via portal when a stock is clicked */}
      {drawerCusip && (
        <StockHistoryDrawer
          cusip={drawerCusip}
          issuerName={drawerName}
          onClose={closeStockDrawer}
        />
      )}
      </StockDrawerCtx.Provider>
    </TickerCtx.Provider>
  );
}

export default App;
