import { useState } from 'react';

export default function HolderBadges({ holders, maxVisible = 4 }) {
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
