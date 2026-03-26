import { useState, useEffect, useMemo, useContext } from 'react';
import { createPortal } from 'react-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TickerCtx } from '../../contexts/TickerContext.js';
import { fmtVal, fmtShares, fmtPeriod } from '../../utils/formatters.js';
import { CHART_COLORS } from '../../constants/chart.js';
import ChartTooltip from './ChartTooltip.jsx';
import Spinner from '../common/Spinner.jsx';
import * as API from '../../api/index.js';

export default function StockHistoryDrawer({ cusip, issuerName, onClose }) {
  const tickerMap               = useContext(TickerCtx);
  const [data, setData]         = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [mode, setMode]         = useState('value'); // 'value' | 'weight' | 'log' | 'shares' | 'qoq'
  const [logScale, setLogScale] = useState(true);   // linear/log toggle for 'value' and 'shares' modes
  const [enabledInsts, setEnabledInsts] = useState(new Set());

  // True when the Y-axis should use logarithmic scale
  const useLogAxis = mode === 'log' || ((mode === 'value' || mode === 'shares') && logScale);

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
    const cd = periods.map((period, periodIdx) => {
      const entry = { period };
      for (const inst of insts) {
        const row = history.find(
          (r) => r.period_of_report === period && r.institution_id === inst.id
        );
        if (row) {
          if (mode === 'value' || mode === 'log') {
            entry[`v_${inst.id}`] = row.value;
          } else if (mode === 'weight') {
            entry[`v_${inst.id}`] = (row.portfolio_weight ?? 0) * 100;
          } else if (mode === 'shares') {
            entry[`v_${inst.id}`] = row.shares;
          } else {
            // qoq: (curr - prev) / prev * 100; 0% on first held quarter
            let prevRow = null;
            for (let pi = periodIdx - 1; pi >= 0; pi--) {
              prevRow = history.find(
                (r) => r.period_of_report === periods[pi] && r.institution_id === inst.id
              );
              if (prevRow) break;
            }
            entry[`v_${inst.id}`] = prevRow && prevRow.shares > 0
              ? (row.shares - prevRow.shares) / prevRow.shares * 100
              : 0;
          }
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

      // Add a close drop point at the next period (skipped when log scale — 0 is invalid on log)
      const lastIdx = periods.indexOf(held[held.length - 1]);
      if (lastIdx < periods.length - 1) {
        const dropPeriod = periods[lastIdx + 1];
        if (!useLogAxis) {
          cd[lastIdx + 1][`v_${inst.id}`] = mode === 'qoq' ? -100 : 0;
          closedPoints.add(`${dropPeriod}::${inst.id}`);
        }
      }
    }

    return { chartData: cd, institutions: insts, openPoints, closedPoints };
  }, [data, mode, logScale]);

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

  const ticker = tickerMap?.get(cusip)?.ticker;

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

        {/* Mode toggle + contextual scale toggle */}
        <div className="px-5 py-2.5 border-b border-gray-50 flex flex-wrap items-center gap-1.5 flex-shrink-0">
          {[['value', 'Market Value'], ['weight', 'Portfolio %'], ['log', 'Log Scale'], ['shares', 'Shares'], ['qoq', 'QoQ Change']].map(([val, label]) => (
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
          {/* Secondary Linear/Log toggle — only visible for Market Value and Shares modes */}
          {(mode === 'value' || mode === 'shares') && (
            <>
              <span className="text-gray-200 select-none mx-0.5">|</span>
              {[['log', 'Log'], ['linear', 'Linear']].map(([val, label]) => (
                <button
                  key={val}
                  onClick={() => setLogScale(val === 'log')}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    (val === 'log') === logScale
                      ? 'bg-gray-700 text-white border-gray-700'
                      : 'text-gray-400 border-gray-200 hover:border-gray-300'
                  }`}
                >{label}</button>
              ))}
            </>
          )}
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
                    scale={useLogAxis ? 'log' : 'auto'}
                    domain={useLogAxis ? ['auto', 'auto'] : undefined}
                    allowDataOverflow={useLogAxis}
                    tickFormatter={
                      (mode === 'value' || mode === 'log')
                        ? fmtVal
                        : mode === 'shares'
                          ? fmtShares
                          : mode === 'qoq'
                            ? (v) => (v >= 0 ? '+' : '') + v.toFixed(1) + '%'
                            : (v) => v.toFixed(1) + '%'
                    }
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    width={64}
                  />
                  <Tooltip content={<ChartTooltip mode={mode} />} />
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
