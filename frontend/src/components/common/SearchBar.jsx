import { useState, useEffect, useRef } from 'react';

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

export default SearchBar;
