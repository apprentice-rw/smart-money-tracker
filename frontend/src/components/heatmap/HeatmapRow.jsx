import { useState, useEffect, useMemo, useContext } from 'react';
import { Treemap, ResponsiveContainer } from 'recharts';
import * as API from '../../api/index.js';
import { TickerCtx } from '../../contexts/TickerContext.js';
import { HeatmapTooltipCtx } from '../../contexts/HeatmapTooltipContext.js';
import { fmtVal, fmtPeriod } from '../../utils/formatters.js';
import { HEATMAP_COLORS, HEATMAP_TEXT, HEATMAP_MAX_CELLS } from '../../constants/heatmap.js';
import HeatmapCell from './HeatmapCell.jsx';

function HeatmapRow({ institution }) {
  const tickerMap = useContext(TickerCtx);

  const [filings,      setFilings]      = useState([]);
  const [period,       setPeriod]       = useState(null);
  const [holdingsData, setHoldingsData] = useState(null);
  const [changes,      setChanges]      = useState(null); // null = not loaded or unavailable
  const [loading,      setLoading]      = useState(false);
  const [tooltip,      setTooltip]      = useState(null); // { x, y, node }

  // Load filings list on mount
  useEffect(() => {
    API.getFilings(institution.id)
      .then((d) => {
        setFilings(d.filings);
        if (d.filings.length > 0) setPeriod(d.filings[0].period_of_report);
      })
      .catch(() => {});
  }, [institution.id]);

  // Load holdings + changes in parallel whenever period changes
  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    setHoldingsData(null);
    setChanges(null);

    const holdingsP = API.getHoldings(institution.id, period);
    const changesP  = API.getChanges(institution.id, period).catch(() => null); // 404 = oldest quarter

    Promise.all([holdingsP, changesP]).then(([h, c]) => {
      if (!cancelled) {
        setHoldingsData(h);
        setChanges(c);
        setLoading(false);
      }
    }).catch(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [institution.id, period]);

  // Build flat Treemap data array from holdings + changes
  const treemapData = useMemo(() => {
    if (!holdingsData) return [];

    // Map cusip → change info
    const changeMap = new Map();
    if (changes) {
      for (const item of changes.changes.new || [])
        changeMap.set(item.cusip, { changeType: 'new', sharesPct: null });
      for (const item of changes.changes.increased || [])
        changeMap.set(item.cusip, { changeType: 'increased', sharesPct: item.shares_pct });
      for (const item of changes.changes.decreased || [])
        changeMap.set(item.cusip, { changeType: 'decreased', sharesPct: item.shares_pct });
      for (const item of changes.changes.closed || [])
        changeMap.set(item.cusip, { changeType: 'closed', sharesPct: null, prevValue: item.prev_value, issuerName: item.issuer_name });
    }

    // Current holdings → cells
    const sorted = [...holdingsData.holdings].sort((a, b) => b.value - a.value);
    const top  = sorted.slice(0, HEATMAP_MAX_CELLS);
    const rest = sorted.slice(HEATMAP_MAX_CELLS);

    const cells = top.map((h) => {
      const ch = changeMap.get(h.cusip) || { changeType: 'unchanged', sharesPct: null };
      return {
        name:       tickerMap?.get(h.cusip)?.ticker || h.issuer_name.slice(0, 12),
        value:      h.value,
        cusip:      h.cusip,
        issuerName: h.issuer_name,
        changeType: ch.changeType,
        sharesPct:  ch.sharesPct ?? null,
      };
    });

    // Closed positions exist in changes but NOT in current holdings
    if (changes) {
      const holdingCusips = new Set(holdingsData.holdings.map((h) => h.cusip));
      for (const item of changes.changes.closed || []) {
        if (!holdingCusips.has(item.cusip)) {
          cells.push({
            name:       tickerMap?.get(item.cusip)?.ticker || item.issuer_name.slice(0, 12),
            value:      item.prev_value || 1, // use prev value for sizing; guard zero
            cusip:      item.cusip,
            issuerName: item.issuer_name,
            changeType: 'closed',
            sharesPct:  null,
          });
        }
      }
    }

    // Aggregate the long tail into one "Other" gray cell
    if (rest.length > 0) {
      cells.push({
        name:       `+${rest.length} more`,
        value:      rest.reduce((s, h) => s + h.value, 0),
        cusip:      null,
        issuerName: `${rest.length} smaller positions`,
        changeType: 'unchanged',
        sharesPct:  null,
      });
    }

    return cells;
  }, [holdingsData, changes, tickerMap]);

  const ticker = tooltip ? tickerMap?.get(tooltip.node.cusip)?.ticker : null;

  return (
    <HeatmapTooltipCtx.Provider value={setTooltip}>
      <div className="flex flex-row items-stretch min-h-[200px] py-2">

        {/* Left panel — institution meta */}
        <div className="w-48 flex-shrink-0 flex flex-col justify-center gap-1.5 px-4 border-r border-gray-100">
          <p className="text-sm font-bold text-gray-900 leading-snug">{institution.display_name || institution.name}</p>
          {holdingsData && (
            <p className="text-xs text-gray-400">{fmtVal(holdingsData.total_value)}</p>
          )}
          {filings.length > 0 && (
            <select
              value={period || ''}
              onChange={(e) => setPeriod(e.target.value)}
              className="mt-1 text-xs border border-gray-200 rounded-lg px-2 py-1 text-gray-600 bg-white
                         focus:outline-none focus:ring-1 focus:ring-blue-400 cursor-pointer
                         hover:border-gray-300 transition-colors"
            >
              {filings.map((f) => (
                <option key={f.id} value={f.period_of_report}>{fmtPeriod(f.period_of_report)}</option>
              ))}
            </select>
          )}
        </div>

        {/* Right panel — Treemap */}
        <div className="flex-1 min-w-0 relative" style={{ height: 200 }}>
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-5 h-5 border-2 border-gray-200 border-t-blue-400 rounded-full animate-spin" />
            </div>
          )}
          {!loading && treemapData.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-xs text-gray-300">
              No holdings data
            </div>
          )}
          {!loading && treemapData.length > 0 && (
            <ResponsiveContainer width="100%" height={200}>
              <Treemap
                data={treemapData}
                dataKey="value"
                aspectRatio={1}
                stroke="transparent"
                isAnimationActive={false}
                content={<HeatmapCell />}
              />
            </ResponsiveContainer>
          )}

          {/* Hover tooltip — fixed positioning uses clientX/Y, correct across scroll */}
          {tooltip && (
            <div
              style={{
                position: 'fixed',
                left: tooltip.x + 14,
                top:  tooltip.y - 12,
                zIndex: 200,
                pointerEvents: 'none',
              }}
              className="bg-white border border-gray-100 rounded-xl shadow-xl px-3 py-2.5 text-xs max-w-[220px]"
            >
              <p className="font-semibold text-gray-900 truncate">{tooltip.node.issuerName}</p>
              {ticker && <p className="text-blue-500 font-bold text-[11px]">{ticker}</p>}
              <p className="text-gray-500 mt-1">{fmtVal(tooltip.node.value)}</p>
              {tooltip.node.sharesPct != null && (
                <p className={tooltip.node.changeType === 'increased' ? 'text-green-600 font-semibold' : 'text-red-500 font-semibold'}>
                  {tooltip.node.sharesPct > 0 ? '+' : ''}{tooltip.node.sharesPct.toFixed(1)}% shares
                </p>
              )}
              <span
                className="inline-block mt-1.5 px-2 py-0.5 rounded text-[10px] font-semibold"
                style={{
                  background: HEATMAP_COLORS[tooltip.node.changeType] || HEATMAP_COLORS.unchanged,
                  color:      HEATMAP_TEXT[tooltip.node.changeType]   || HEATMAP_TEXT.unchanged,
                }}
              >
                {tooltip.node.changeType}
              </span>
            </div>
          )}
        </div>
      </div>
    </HeatmapTooltipCtx.Provider>
  );
}

export default HeatmapRow;
