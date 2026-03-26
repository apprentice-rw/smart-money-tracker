import { useState } from 'react';

function ShowMoreTable({ items, defaultRows = 5, renderRow, emptyMsg = 'No results' }) {
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

export default ShowMoreTable;
