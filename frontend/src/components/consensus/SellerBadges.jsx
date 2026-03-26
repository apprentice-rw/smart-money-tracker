import { useState } from 'react';

export default function SellerBadges({ sellers, maxVisible = 4 }) {
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
