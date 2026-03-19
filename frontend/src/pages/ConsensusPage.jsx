import React, { useState, useEffect, useContext, useCallback } from 'react';
import * as API from '../api.js';
import { TickerCtx, StockDrawerCtx } from '../contexts.js';

// ── Utilities ───────────────────────────────────────────────────────────────

function fmtVal(v) {
  if (v == null) return '—';
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v}`;
}

function fmtPeriod(s) {
  if (!s) return '';
  const [year, month] = s.split('-');
  return `Q${Math.ceil(parseInt(month, 10) / 3)} ${year}`;
}

// ── HolderBadges ────────────────────────────────────────────────────────────

function HolderBadges({ holders, maxVisible = 4 }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? holders : holders.slice(0, maxVisible);
  const remaining = holders.length - maxVisible;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {visible.map((h) => (
        <span
          key={h.institution_id}
          className="bg-gray-100 text-gray-600 text-xs rounded-full px-2 py-0.5 whitespace-nowrap"
        >
          {h.name}
        </span>
      ))}
      {!expanded && remaining > 0 && (
        <button
          onClick={(e) => { e.stopPropagation(); setExpanded(true); }}
          className="text-xs text-blue-500 hover:text-blue-700 px-1"
        >
          +{remaining} more
        </button>
      )}
    </div>
  );
}

// ── BuyerBadges — shows change type color ───────────────────────────────────

function BuyerBadges({ buyers, maxVisible = 4 }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? buyers : buyers.slice(0, maxVisible);
  const remaining = buyers.length - maxVisible;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {visible.map((b) => (
        <span
          key={b.institution_id}
          className={`text-xs rounded-full px-2 py-0.5 whitespace-nowrap ${
            b.change_type === 'new'
              ? 'bg-green-100 text-green-700'
              : 'bg-emerald-50 text-emerald-700'
          }`}
        >
          {b.name}{b.change_type === 'new' ? ' ★' : ''}
        </span>
      ))}
      {!expanded && remaining > 0 && (
        <button
          onClick={(e) => { e.stopPropagation(); setExpanded(true); }}
          className="text-xs text-blue-500 hover:text-blue-700 px-1"
        >
          +{remaining} more
        </button>
      )}
    </div>
  );
}

function SellerBadges({ sellers, maxVisible = 4 }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? sellers : sellers.slice(0, maxVisible);
  const remaining = sellers.length - maxVisible;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {visible.map((s) => (
        <span
          key={s.institution_id}
          className={`text-xs rounded-full px-2 py-0.5 whitespace-nowrap ${
            s.change_type === 'closed'
              ? 'bg-red-100 text-red-700'
              : 'bg-orange-50 text-orange-700'
          }`}
        >
          {s.name}{s.change_type === 'closed' ? ' ✕' : ''}
        </span>
      ))}
      {!expanded && remaining > 0 && (
        <button
          onClick={(e) => { e.stopPropagation(); setExpanded(true); }}
          className="text-xs text-blue-500 hover:text-blue-700 px-1"
        >
          +{remaining} more
        </button>
      )}
    </div>
  );
}

// ── ModuleCard wrapper ───────────────────────────────────────────────────────

function ModuleCard({ title, subtitle, count, children, fullWidth = false }) {
  return (
    <div className={`bg-white rounded-2xl shadow-sm border border-gray-100 p-5 ${fullWidth ? 'lg:col-span-2' : ''}`}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
          {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
        </div>
        {count != null && (
          <span className="bg-gray-100 text-gray-500 text-xs font-medium rounded-full px-2.5 py-1">
            {count}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

// ── ShowMoreTable — wraps a list with show more/less ────────────────────────

function ShowMoreTable({ items, defaultRows = 10, renderRow, emptyMsg = 'No results' }) {
  const [expanded, setExpanded] = useState(false);
  if (!items || items.length === 0) {
    return <p className="text-xs text-gray-400 py-4 text-center">{emptyMsg}</p>;
  }
  const visible = expanded ? items : items.slice(0, defaultRows);
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          {visible.map((item, i) => renderRow(item, i))}
        </table>
      </div>
      {items.length > defaultRows && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 text-xs text-blue-500 hover:text-blue-700 w-full text-center py-1"
        >
          {expanded ? 'Show less' : `Show ${items.length - defaultRows} more`}
        </button>
      )}
    </div>
  );
}

// ── Module: Top Consensus Holdings ──────────────────────────────────────────

function HoldingsModule({ data, onStockClick, tickerMap }) {
  if (!data) return <ModuleSpinner />;
  return (
    <ModuleCard
      title="Top Consensus Holdings"
      subtitle="Stocks held by the most institutions"
      count={data.results?.length}
    >
      <ShowMoreTable
        items={data.results}
        emptyMsg="No consensus holdings found"
        renderRow={(item, i) => (
          <tr
            key={item.cusip}
            onClick={() => onStockClick(item.cusip, item.issuer_name)}
            className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
          >
            <td className="py-2 pr-3 text-gray-400 w-6 align-top">{i + 1}</td>
            <td className="py-2 pr-3 align-top">
              <div className="font-medium text-gray-900">
                {tickerMap?.[item.cusip] || item.issuer_name}
              </div>
              {tickerMap?.[item.cusip] && (
                <div className="text-gray-400 text-xs">{item.issuer_name}</div>
              )}
              <HolderBadges holders={item.holders} />
            </td>
            <td className="py-2 pl-2 text-right align-top whitespace-nowrap">
              <div className="font-medium text-gray-900">{fmtVal(item.total_value)}</div>
              <div className="text-gray-400">{item.holder_count} holders</div>
            </td>
          </tr>
        )}
      />
    </ModuleCard>
  );
}

// ── Module: Consensus Buying ─────────────────────────────────────────────────

function BuyingModule({ data, onStockClick, tickerMap }) {
  if (!data) return <ModuleCard title="Consensus Buying" subtitle="Loading..."><ModuleSpinner /></ModuleCard>;
  return (
    <ModuleCard
      title="Consensus Buying"
      subtitle={data.prev_period ? `New/increased vs ${fmtPeriod(data.prev_period)}` : 'New & increased positions'}
      count={data.results?.length}
    >
      <ShowMoreTable
        items={data.results}
        emptyMsg="No consensus buying found"
        renderRow={(item, i) => (
          <tr
            key={item.cusip}
            onClick={() => onStockClick(item.cusip, item.issuer_name)}
            className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
          >
            <td className="py-2 pr-3 text-gray-400 w-6 align-top">{i + 1}</td>
            <td className="py-2 pr-3 align-top">
              <div className="font-medium text-gray-900">
                {tickerMap?.[item.cusip] || item.issuer_name}
              </div>
              {tickerMap?.[item.cusip] && (
                <div className="text-gray-400 text-xs">{item.issuer_name}</div>
              )}
              <BuyerBadges buyers={item.buyers} />
            </td>
            <td className="py-2 pl-2 text-right align-top whitespace-nowrap">
              <div className="font-medium text-gray-900">{fmtVal(item.total_curr_value)}</div>
              <div className="text-green-600">{item.buyer_count} buyers</div>
            </td>
          </tr>
        )}
      />
    </ModuleCard>
  );
}

// ── Module: Consensus Selling ────────────────────────────────────────────────

function SellingModule({ data, onStockClick, tickerMap }) {
  if (!data) return <ModuleCard title="Consensus Selling" subtitle="Loading..."><ModuleSpinner /></ModuleCard>;
  return (
    <ModuleCard
      title="Consensus Selling"
      subtitle={data.prev_period ? `Closed/decreased vs ${fmtPeriod(data.prev_period)}` : 'Closed & decreased positions'}
      count={data.results?.length}
    >
      <ShowMoreTable
        items={data.results}
        emptyMsg="No consensus selling found"
        renderRow={(item, i) => (
          <tr
            key={item.cusip}
            onClick={() => onStockClick(item.cusip, item.issuer_name)}
            className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
          >
            <td className="py-2 pr-3 text-gray-400 w-6 align-top">{i + 1}</td>
            <td className="py-2 pr-3 align-top">
              <div className="font-medium text-gray-900">
                {tickerMap?.[item.cusip] || item.issuer_name}
              </div>
              {tickerMap?.[item.cusip] && (
                <div className="text-gray-400 text-xs">{item.issuer_name}</div>
              )}
              <SellerBadges sellers={item.sellers} />
            </td>
            <td className="py-2 pl-2 text-right align-top whitespace-nowrap">
              <div className="font-medium text-gray-900">{fmtVal(item.total_prev_value)}</div>
              <div className="text-red-500">{item.seller_count} sellers</div>
            </td>
          </tr>
        )}
      />
    </ModuleCard>
  );
}

// ── Module: Emerging Consensus ───────────────────────────────────────────────

function EmergingModule({ data, onStockClick, tickerMap }) {
  if (!data) return <ModuleCard title="Emerging Consensus" subtitle="Loading..."><ModuleSpinner /></ModuleCard>;
  return (
    <ModuleCard
      title="Emerging Consensus"
      subtitle={data.prev_period ? `Holder count growing vs ${fmtPeriod(data.prev_period)}` : 'Growing institutional interest'}
      count={data.results?.length}
    >
      <ShowMoreTable
        items={data.results}
        emptyMsg="No emerging consensus found (requires prior quarter data)"
        renderRow={(item, i) => (
          <tr
            key={item.cusip}
            onClick={() => onStockClick(item.cusip, item.issuer_name)}
            className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
          >
            <td className="py-2 pr-3 text-gray-400 w-6 align-top">{i + 1}</td>
            <td className="py-2 pr-3 align-top">
              <div className="font-medium text-gray-900">
                {tickerMap?.[item.cusip] || item.issuer_name}
              </div>
              {tickerMap?.[item.cusip] && (
                <div className="text-gray-400 text-xs">{item.issuer_name}</div>
              )}
            </td>
            <td className="py-2 pl-2 text-right align-top whitespace-nowrap">
              <div className="font-medium text-green-600">+{item.holder_delta} holders</div>
              <div className="text-gray-400">{item.prev_holders} → {item.curr_holders}</div>
              <div className="text-gray-500">{fmtVal(item.total_value)}</div>
            </td>
          </tr>
        )}
      />
    </ModuleCard>
  );
}

// ── Module: Persistent Holdings ──────────────────────────────────────────────

function PersistentModule({ data, onStockClick, tickerMap }) {
  if (!data) return (
    <ModuleCard title="Persistent Holdings" subtitle="Loading..." fullWidth>
      <ModuleSpinner />
    </ModuleCard>
  );
  return (
    <ModuleCard
      title="Persistent Holdings"
      subtitle={`Held for ${data.min_quarters}+ quarters of ${data.total_quarters_available} available`}
      count={data.results?.length}
      fullWidth
    >
      <ShowMoreTable
        items={data.results}
        emptyMsg="No persistent holdings found with current filters"
        renderRow={(item, i) => (
          <tr
            key={item.cusip}
            onClick={() => onStockClick(item.cusip, item.issuer_name)}
            className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
          >
            <td className="py-2 pr-3 text-gray-400 w-6 align-top">{i + 1}</td>
            <td className="py-2 pr-3 align-top min-w-[160px]">
              <div className="font-medium text-gray-900">
                {tickerMap?.[item.cusip] || item.issuer_name}
              </div>
              {tickerMap?.[item.cusip] && (
                <div className="text-gray-400 text-xs">{item.issuer_name}</div>
              )}
              <HolderBadges holders={item.holders} />
            </td>
            <td className="py-2 px-3 text-right align-top whitespace-nowrap">
              <div className="font-medium text-gray-900">{item.persistent_holder_count} institutions</div>
              <div className="text-gray-400">max {item.max_quarters_held}Q held</div>
            </td>
            <td className="py-2 pl-2 text-right align-top whitespace-nowrap">
              <div className="font-medium text-gray-900">{fmtVal(item.latest_total_value)}</div>
              <div className="text-gray-400">latest value</div>
            </td>
          </tr>
        )}
      />
    </ModuleCard>
  );
}

// ── Spinner ──────────────────────────────────────────────────────────────────

function ModuleSpinner() {
  return (
    <div className="flex justify-center py-8">
      <div className="w-5 h-5 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin" />
    </div>
  );
}

// ── QuarterSelector ──────────────────────────────────────────────────────────

function QuarterSelector({ quarters, selected, onSelect }) {
  const [open, setOpen] = useState(false);
  if (!quarters.length) return null;

  function fmtQ(s) {
    if (!s) return '';
    const [year, month] = s.split('-');
    return `Q${Math.ceil(parseInt(month, 10) / 3)} ${year}`;
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-sm font-medium text-gray-700
                   border border-gray-200 rounded-lg px-3 py-1.5 bg-white shadow-sm
                   hover:border-gray-300 transition-colors"
      >
        {fmtQ(selected)}
        <svg className="w-3.5 h-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-lg z-20 py-1 min-w-[120px]">
            {quarters.map((q) => (
              <button
                key={q}
                onClick={() => { onSelect(q); setOpen(false); }}
                className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 transition-colors ${
                  q === selected ? 'font-semibold text-gray-900' : 'text-gray-600'
                }`}
              >
                {fmtQ(q)}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── ConsensusPage ────────────────────────────────────────────────────────────

export default function ConsensusPage({ tickerMap: tickerMapProp, onStockClick: onStockClickProp }) {
  // Try context first, fall back to props (for flexibility)
  const ctxTickers  = useContext(TickerCtx);
  const ctxDrawer   = useContext(StockDrawerCtx);
  const tickerMap   = ctxTickers  ?? tickerMapProp  ?? {};
  const openDrawer  = ctxDrawer   ?? onStockClickProp ?? (() => {});

  const [quarters,       setQuarters]       = useState([]);
  const [selectedQ,      setSelectedQ]      = useState(null);
  const [holdingsData,   setHoldingsData]   = useState(null);
  const [buyingData,     setBuyingData]     = useState(null);
  const [sellingData,    setSellingData]    = useState(null);
  const [emergingData,   setEmergingData]   = useState(null);
  const [persistentData, setPersistentData] = useState(null);
  const [loading,        setLoading]        = useState(false);
  const [moduleErrors,   setModuleErrors]   = useState({});

  // Load quarter list on mount
  useEffect(() => {
    API.getConsensusQuarters().then(({ quarters: qs }) => {
      setQuarters(qs);
      if (qs.length) setSelectedQ(qs[0]);
    }).catch(console.error);
  }, []);

  // Fetch all modules when quarter changes
  const fetchAll = useCallback((period) => {
    setLoading(true);
    setHoldingsData(null);
    setBuyingData(null);
    setSellingData(null);
    setEmergingData(null);
    setPersistentData(null);
    setModuleErrors({});

    const safe = (promise, setter, key) =>
      promise.then(setter).catch((e) => setModuleErrors((prev) => ({ ...prev, [key]: e.message })));

    Promise.all([
      safe(API.getConsensusHoldings(period, 1, 50),  setHoldingsData,   'holdings'),
      safe(API.getConsensusBuying(period, 1, 50),    setBuyingData,     'buying'),
      safe(API.getConsensusSelling(period, 1, 50),   setSellingData,    'selling'),
      safe(API.getConsensusEmerging(period, 50),     setEmergingData,   'emerging'),
      safe(API.getConsensusPersistent(2, 1, 50),     setPersistentData, 'persistent'),
    ]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedQ) fetchAll(selectedQ);
  }, [selectedQ, fetchAll]);

  function handleStockClick(cusip, issuerName) {
    openDrawer(cusip, issuerName);
  }

  const totalInstitutions = holdingsData?.total_institutions ?? null;
  const quarterCount      = quarters.length;

  return (
    <div>
      {/* Page toolbar */}
      <div className="max-w-7xl mx-auto px-8 pt-5 pb-3">
        <div className="flex items-start justify-between gap-4 mb-1">
          <div>
            <h1 className="text-lg font-semibold text-gray-900">Consensus</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Cross-institutional signals · {quarterCount > 0 ? `${quarterCount} quarters` : ''}
              {totalInstitutions != null ? ` · ${totalInstitutions} institutions` : ''}
            </p>
          </div>
          <QuarterSelector
            quarters={quarters}
            selected={selectedQ}
            onSelect={setSelectedQ}
          />
        </div>
      </div>

      {/* Module grid */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {loading && !holdingsData && (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin" />
          </div>
        )}

        {selectedQ && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Module 1: Holdings */}
            {moduleErrors.holdings ? (
              <ModuleError title="Top Consensus Holdings" message={moduleErrors.holdings} />
            ) : (
              <HoldingsModule data={holdingsData} onStockClick={handleStockClick} tickerMap={tickerMap} />
            )}

            {/* Module 2: Buying */}
            {moduleErrors.buying ? (
              <ModuleError title="Consensus Buying" message={moduleErrors.buying} />
            ) : (
              <BuyingModule data={buyingData} onStockClick={handleStockClick} tickerMap={tickerMap} />
            )}

            {/* Module 3: Selling */}
            {moduleErrors.selling ? (
              <ModuleError title="Consensus Selling" message={moduleErrors.selling} />
            ) : (
              <SellingModule data={sellingData} onStockClick={handleStockClick} tickerMap={tickerMap} />
            )}

            {/* Module 4: Emerging */}
            {moduleErrors.emerging ? (
              <ModuleError title="Emerging Consensus" message={moduleErrors.emerging} />
            ) : (
              <EmergingModule data={emergingData} onStockClick={handleStockClick} tickerMap={tickerMap} />
            )}

            {/* Module 5: Persistent (full width) */}
            {moduleErrors.persistent ? (
              <ModuleError title="Persistent Holdings" message={moduleErrors.persistent} fullWidth />
            ) : (
              <PersistentModule data={persistentData} onStockClick={handleStockClick} tickerMap={tickerMap} />
            )}
          </div>
        )}

        <footer className="mt-14 text-center text-xs text-gray-400">
          Smart Money Tracker · SEC EDGAR 13F data
        </footer>
      </div>
    </div>
  );
}

function ModuleError({ title, message, fullWidth = false }) {
  return (
    <ModuleCard title={title} fullWidth={fullWidth}>
      <p className="text-xs text-red-500 py-4">{message}</p>
    </ModuleCard>
  );
}
