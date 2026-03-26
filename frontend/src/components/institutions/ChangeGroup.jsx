import { useState, useEffect, useMemo } from 'react';
import { sortItems } from '../../utils/sortUtils.js';
import SectionHeader from '../common/SectionHeader.jsx';
import ChangeRow from './ChangeRow.jsx';

const DEFAULT_VISIBLE = 3;

export default function ChangeGroup({ items, type, label, sortKey }) {
  const [showAll, setShowAll] = useState(false);

  // Reset "show more" whenever sort order changes
  useEffect(() => { setShowAll(false); }, [sortKey]);

  // Memoised sort — only recomputes when items, sortKey, or type change.
  // Safe for large datasets (e.g. RenTech's 1 600+ decreased rows).
  const sorted = useMemo(() => sortItems(items, sortKey, type), [items, sortKey, type]);

  if (!items || items.length === 0) return null;

  const visible    = showAll ? sorted : sorted.slice(0, DEFAULT_VISIBLE);
  const hiddenCount = items.length - DEFAULT_VISIBLE;

  return (
    <div>
      <SectionHeader type={type} label={label} count={items.length} />
      <div>
        {visible.map((item) => (
          <ChangeRow key={`${item.cusip}-${type}`} item={item} type={type} sortKey={sortKey} />
        ))}
      </div>
      {!showAll && hiddenCount > 0 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-1.5 text-xs text-blue-600 hover:text-blue-700 font-medium"
        >
          Show {hiddenCount} more ↓
        </button>
      )}
      {showAll && items.length > DEFAULT_VISIBLE && (
        <button
          onClick={() => setShowAll(false)}
          className="mt-1.5 text-xs text-gray-400 hover:text-gray-600 font-medium"
        >
          Show less ↑
        </button>
      )}
    </div>
  );
}
