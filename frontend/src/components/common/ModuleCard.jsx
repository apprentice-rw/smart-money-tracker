
function ModuleCard({ title, subtitle, children, fullWidth = false, collapsed = false, onCollapseToggle }) {
  return (
    <div className={`bg-white rounded-2xl shadow-sm border border-gray-100 p-5 ${fullWidth ? 'lg:col-span-2' : ''} ${collapsed ? 'self-start' : ''}`}>
      <div className={`flex items-center justify-between ${!collapsed ? 'mb-4' : ''}`}>
        <div>
          <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
          {!collapsed && subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
        </div>
        {onCollapseToggle && (
          <button
            onClick={onCollapseToggle}
            title={collapsed ? 'Expand' : 'Collapse'}
            className="p-1 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <svg
              className={`w-4 h-4 transition-transform duration-200 ${collapsed ? 'rotate-180' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
            </svg>
          </button>
        )}
      </div>
      {!collapsed && children}
    </div>
  );
}

export default ModuleCard;
