import { useState } from 'react';

export default function QuarterSelector({ quarters, selected, onSelect }) {
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
                key={q.period}
                onClick={() => { onSelect(q.period); setOpen(false); }}
                className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 transition-colors ${
                  q.period === selected ? 'font-semibold text-gray-900' : 'text-gray-600'
                }`}
              >
                {fmtQ(q.period)}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
