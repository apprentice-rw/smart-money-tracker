import { useState, useEffect, useRef, Fragment } from 'react';
import { useCardOrder } from '../hooks/useCardOrder.js';
import { useDragAndDrop } from '../hooks/useDragAndDrop.js';
import { useCollapse } from '../hooks/useCollapse.js';
import InstitutionCard from '../components/institutions/InstitutionCard.jsx';
import HeatmapRow from '../components/heatmap/HeatmapRow.jsx';
import SearchBar from '../components/common/SearchBar.jsx';
import CardErrorBoundary from '../components/common/CardErrorBoundary.jsx';
import { HEATMAP_COLORS } from '../constants/heatmap.js';

export default function InstitutionsPage({ institutions = [], error }) {
  // ── View (cards / heatmap) ────────────────────────────────────
  const [view, setView] = useState(() =>
    localStorage.getItem('smt_view') || 'cards'
  );
  function switchView(v) {
    setView(v);
    localStorage.setItem('smt_view', v);
  }

  const [highlightId, setHighlightId] = useState(null);

  // ── Card refs map (for scroll-to from SearchBar) ───────────────
  const cardRefsMap = useRef({});
  useEffect(() => {
    institutions.forEach((inst) => {
      if (!cardRefsMap.current[inst.id]) {
        cardRefsMap.current[inst.id] = { current: null };
      }
    });
  }, [institutions]);

  // ── Card ordering + AUM ────────────────────────────────────────
  const {
    setCardOrder,
    handleAumLoaded,
    orderedInsts,
    orderedInstsRef,
    resetOrder,
  } = useCardOrder(institutions);

  // ── Drag-and-drop ──────────────────────────────────────────────
  const { draggingId, dragOverId, handleHandleMouseDown } = useDragAndDrop(orderedInstsRef, setCardOrder);

  // ── Collapse helpers ───────────────────────────────────────────
  const { collapsedMap, toggleCollapse, collapseAll, expandAll } = useCollapse();

  const allCollapsed = institutions.length > 0
    && institutions.every(i => collapsedMap[i.id]);

  return (
    <>
      {/* Page toolbar */}
      <div className="max-w-7xl mx-auto px-8 pt-5 pb-3">
        <div className="flex items-start justify-between gap-4 mb-3">
          <div>
            <h1 className="text-lg font-semibold text-gray-900">Institutions</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              SEC 13F filings · institutional position changes
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 mt-1">
            {view === 'cards' && (
              <>
                <button
                  onClick={allCollapsed ? expandAll : () => collapseAll(institutions)}
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
              </>
            )}
            <div className="flex rounded-lg border border-gray-200 overflow-hidden bg-white shadow-sm">
              {[['cards', '≡ Cards'], ['heatmap', '▦ Heatmap']].map(([v, label]) => (
                <button
                  key={v}
                  onClick={() => switchView(v)}
                  className={`text-xs px-3 py-1.5 transition-colors ${
                    view === v
                      ? 'bg-gray-100 text-gray-900 font-semibold'
                      : 'text-gray-400 hover:text-gray-700'
                  }`}
                >{label}</button>
              ))}
            </div>
          </div>
        </div>
        <div className="max-w-2xl">
          <SearchBar institutions={institutions} cardRefsMap={cardRefsMap} setHighlightId={setHighlightId} />
        </div>
      </div>

      {/* Content area */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {error && (
          <div className="mb-6 bg-red-50 border border-red-100 rounded-xl px-5 py-4 text-sm text-red-600">
            Could not reach the API — make sure the server is running at{' '}
            <code className="font-mono">http://127.0.0.1:8000</code>.
            <br />
            <span className="text-red-400 text-xs mt-1 block">{error}</span>
          </div>
        )}
        {institutions.length === 0 && !error && (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin" />
          </div>
        )}
        {view === 'cards' ? (
          <div className="relative z-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 items-start">
            {orderedInsts.map((inst) => {
              const isDragging = draggingId === inst.id;
              const isTarget   = dragOverId  === inst.id && !isDragging;
              return (
                <Fragment key={inst.id}>
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
                </Fragment>
              );
            })}
          </div>
        ) : (
          <div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-4 px-1 text-xs text-gray-500">
              {[
                ['new',       'New position'],
                ['increased', 'Increased'],
                ['decreased', 'Decreased'],
                ['closed',    'Closed / sold'],
                ['unchanged', 'Unchanged'],
              ].map(([type, label]) => (
                <div key={type} className="flex items-center gap-1.5">
                  <span
                    className="w-3 h-3 rounded-sm flex-shrink-0"
                    style={{ background: HEATMAP_COLORS[type] }}
                  />
                  {label}
                </div>
              ))}
              <span className="text-gray-300 ml-auto">Block size = portfolio weight · Hover for details</span>
            </div>
            <div className="bg-white rounded-3xl shadow-lg divide-y divide-gray-100 overflow-hidden">
              {orderedInsts.map((inst) => (
                <HeatmapRow key={inst.id} institution={inst} />
              ))}
            </div>
          </div>
        )}
        <footer className="mt-14 text-center text-xs text-gray-400">
          Smart Money Tracker · SEC EDGAR 13F data
        </footer>
      </div>
    </>
  );
}
