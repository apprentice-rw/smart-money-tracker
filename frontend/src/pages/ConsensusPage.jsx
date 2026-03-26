import { useState, useEffect, useContext, useCallback } from 'react';
import * as API from '../api/index.js';
import { TickerCtx } from '../contexts/TickerContext.js';
import { StockDrawerCtx } from '../contexts/DrawerContext.js';
import { periodRange, fmtFilingDate } from '../utils/dateUtils.js';
import HoldingsModule from '../components/consensus/HoldingsModule.jsx';
import BuyingModule from '../components/consensus/BuyingModule.jsx';
import SellingModule from '../components/consensus/SellingModule.jsx';
import EmergingModule from '../components/consensus/EmergingModule.jsx';
import PersistentModule from '../components/consensus/PersistentModule.jsx';
import ModuleError from '../components/consensus/ModuleError.jsx';
import QuarterSelector from '../components/consensus/QuarterSelector.jsx';

// ── ConsensusPage ────────────────────────────────────────────────────────────

export default function ConsensusPage({ tickerMap: tickerMapProp, onStockClick: onStockClickProp }) {
  // Try context first, fall back to props (for flexibility)
  const ctxTickers  = useContext(TickerCtx);
  const ctxDrawer   = useContext(StockDrawerCtx);
  // B1: TickerCtx provides a Map object — convert to plain object for bracket access
  const rawTickers  = ctxTickers ?? tickerMapProp ?? {};
  const tickerMap   = rawTickers instanceof Map ? Object.fromEntries(rawTickers) : rawTickers;
  const openDrawer  = ctxDrawer ?? onStockClickProp ?? (() => {});

  const [quarters,       setQuarters]       = useState([]);   // array of {period, filing_date_min, filing_date_max}
  const [selectedQ,      setSelectedQ]      = useState(null); // period string
  const [holdingsData,   setHoldingsData]   = useState(null);
  const [buyingData,     setBuyingData]     = useState(null);
  const [sellingData,    setSellingData]    = useState(null);
  const [emergingData,   setEmergingData]   = useState(null);
  const [persistentData, setPersistentData] = useState(null);
  const [loading,        setLoading]        = useState(false);
  const [moduleErrors,   setModuleErrors]   = useState({});
  const [collapsedModules, setCollapsedModules] = useState({});

  const MODULE_IDS = ['holdings', 'buying', 'selling', 'emerging', 'persistent'];
  function toggleModule(id) { setCollapsedModules(prev => ({ ...prev, [id]: !prev[id] })); }
  function collapseAllModules() { setCollapsedModules(Object.fromEntries(MODULE_IDS.map(id => [id, true]))); }
  function expandAllModules() { setCollapsedModules({}); }
  const allModulesCollapsed = MODULE_IDS.every(id => collapsedModules[id]);

  // Load quarter list on mount
  useEffect(() => {
    API.getConsensusQuarters().then(({ quarters: qs }) => {
      // Normalize: handle old string format and new object format
      const normalized = qs.map((q) =>
        typeof q === 'string'
          ? { period: q, filing_date_min: null, filing_date_max: null }
          : q
      );
      setQuarters(normalized);
      if (normalized.length) setSelectedQ(normalized[0].period);
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
  const selectedMeta      = quarters.find((q) => q.period === selectedQ);

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
            {selectedMeta && (
              <p className="text-xs text-gray-400 mt-1">
                Period: {periodRange(selectedMeta.period)}
                {selectedMeta.filing_date_min && selectedMeta.filing_date_max && (() => {
                  const filedMin = fmtFilingDate(selectedMeta.filing_date_min);
                  const filedMax = fmtFilingDate(selectedMeta.filing_date_max);
                  const filedStr = filedMin === filedMax ? filedMin : `${filedMin} – ${filedMax}`;
                  return <> · Filed: {filedStr}</>;
                })()}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={allModulesCollapsed ? expandAllModules : collapseAllModules}
              className="text-xs text-gray-400 hover:text-gray-700
                         border border-gray-200 hover:border-gray-300 rounded-lg
                         px-3 py-1.5 transition-colors bg-white shadow-sm"
            >
              {allModulesCollapsed ? 'Expand All' : 'Collapse All'}
            </button>
            <QuarterSelector
              quarters={quarters}
              selected={selectedQ}
              onSelect={setSelectedQ}
            />
          </div>
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
              <HoldingsModule data={holdingsData} onStockClick={handleStockClick} tickerMap={tickerMap} collapsed={!!collapsedModules.holdings} onCollapseToggle={() => toggleModule('holdings')} />
            )}

            {/* Module 2: Buying */}
            {moduleErrors.buying ? (
              <ModuleError title="Consensus Buying" message={moduleErrors.buying} />
            ) : (
              <BuyingModule data={buyingData} onStockClick={handleStockClick} tickerMap={tickerMap} collapsed={!!collapsedModules.buying} onCollapseToggle={() => toggleModule('buying')} />
            )}

            {/* Module 3: Selling */}
            {moduleErrors.selling ? (
              <ModuleError title="Consensus Selling" message={moduleErrors.selling} />
            ) : (
              <SellingModule data={sellingData} onStockClick={handleStockClick} tickerMap={tickerMap} collapsed={!!collapsedModules.selling} onCollapseToggle={() => toggleModule('selling')} />
            )}

            {/* Module 4: Emerging */}
            {moduleErrors.emerging ? (
              <ModuleError title="Emerging Consensus" message={moduleErrors.emerging} />
            ) : (
              <EmergingModule data={emergingData} onStockClick={handleStockClick} tickerMap={tickerMap} collapsed={!!collapsedModules.emerging} onCollapseToggle={() => toggleModule('emerging')} />
            )}

            {/* Module 5: Persistent (full width) */}
            {moduleErrors.persistent ? (
              <ModuleError title="Persistent Holdings" message={moduleErrors.persistent} fullWidth />
            ) : (
              <PersistentModule data={persistentData} onStockClick={handleStockClick} tickerMap={tickerMap} collapsed={!!collapsedModules.persistent} onCollapseToggle={() => toggleModule('persistent')} />
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
