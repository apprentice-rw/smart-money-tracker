import { NavLink } from 'react-router-dom';

export default function Navbar() {
  return (
    <nav className="bg-white/90 backdrop-blur-sm border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-8 h-14 flex items-center justify-between">

        {/* Left: Tidemark wordmark */}
        <span className="text-xl font-bold tracking-tight text-gray-900">
          Tidemark
        </span>

        {/* Center: Nav links */}
        <div className="flex items-center gap-8">
          {[
            { to: '/institutions', label: 'Institutions' },
            { to: '/consensus',    label: 'Consensus' },
            { to: '/stocks',       label: 'Stocks' },
          ].map(({ to, label }) => (
            <NavLink key={to} to={to}
              className={({ isActive }) =>
                `text-sm pb-0.5 transition-colors ${
                  isActive
                    ? 'font-semibold text-gray-900 border-b-2 border-gray-900'
                    : 'text-gray-400 hover:text-gray-600'
                }`
              }
            >{label}</NavLink>
          ))}
        </div>

        {/* Right: placeholder to balance wordmark */}
        <div className="w-20" />

      </div>
    </nav>
  );
}
