import { useState } from 'react';

export default function BuyerBadges({ buyers, maxVisible = 4 }) {
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
