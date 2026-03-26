import { useState, useEffect } from 'react';
import * as API from '../../api/index.js';
import { fmtVal, fmtPeriod } from '../../utils/formatters.js';
import SortPills from '../common/SortPills.jsx';
import Spinner from '../common/Spinner.jsx';
import ChangeGroup from './ChangeGroup.jsx';
import HoldingsSection from './HoldingsSection.jsx';
import StatsBar from './StatsBar.jsx';

export default function InstitutionCard({ institution, onAumLoaded, onDragHandleMouseDown, collapsed, onCollapseToggle }) {
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

  const [sortKey, setSortKey] = useState('value');
  const [sortDir, setSortDir] = useState('desc');
  const sortKeyFull = `${sortKey}_${sortDir}`;

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
    <div className="bg-white rounded-3xl shadow-lg overflow-hidden flex flex-col">

      {/* ── Card header (always visible) ── */}
      <div className={`px-5 pt-5 border-b border-gray-50 ${!collapsed ? 'pb-3' : 'pb-4'}`}>
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
                {institution.display_name || institution.name}
              </h2>
              {/* AUM shown inline when collapsed */}
              {collapsed && holdingsData && (
                <span className="text-sm font-semibold text-gray-400">
                  {fmtVal(holdingsData.total_value)}
                </span>
              )}
            </div>
            {!collapsed && currentFiling && (
              <div className="mt-1">
                <span className="text-[11px] text-gray-400">
                  filed {currentFiling.filing_date}
                </span>
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

        {/* Sort pills — only shown when changes data is present or loading (hidden on error/oldest quarter) */}
        {!collapsed && (changes || changesLoading) && (
          <div className="flex items-center gap-2 pt-3">
            <span className="text-[11px] text-gray-400">Sort:</span>
            <SortPills
              options={[{key:'value',label:'Value'},{key:'pct',label:'% Chg'},{key:'shares',label:'Shares'}]}
              sortKey={sortKey}
              sortDir={sortDir}
              onChange={(key, dir) => { setSortKey(key); setSortDir(dir); }}
            />
          </div>
        )}
      </div>

      {/* ── Card body (hidden when collapsed) ── */}
      {!collapsed && (
        <div className="px-5 py-4 overflow-y-auto overflow-x-hidden max-h-[600px] thin-scroll">

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

              <ChangeGroup items={changes.changes.new}       type="new"       label="New Positions" sortKey={sortKeyFull} />
              <ChangeGroup items={changes.changes.increased} type="increased" label="Increased"      sortKey={sortKeyFull} />
              <ChangeGroup items={changes.changes.decreased} type="decreased" label="Decreased"      sortKey={sortKeyFull} />
              <ChangeGroup items={changes.changes.closed}    type="closed"    label="Closed"         sortKey={sortKeyFull} />
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
