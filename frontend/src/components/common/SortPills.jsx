
function SortPills({ options, sortKey, sortDir, onChange, bordered = false }) {
  return (
    <div className={`flex gap-1 mb-3${bordered ? ' border border-gray-200' : ''}`}>
      {options.map(({ key, label }) => {
        const active = key === sortKey;
        return (
          <button
            key={key}
            onClick={() => {
              if (active) {
                onChange(key, sortDir === 'desc' ? 'asc' : 'desc');
              } else {
                onChange(key, 'desc');
              }
            }}
            className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
              active
                ? 'bg-gray-200 text-gray-900 font-semibold'
                : 'bg-transparent text-gray-400 hover:text-gray-600'
            }`}
          >
            {label}{active ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
          </button>
        );
      })}
    </div>
  );
}

export default SortPills;
