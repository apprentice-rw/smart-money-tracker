import { SECTION_STYLES } from '../../constants/sections.js';

function SectionHeader({ type, label, count }) {
  const s = SECTION_STYLES[type] || SECTION_STYLES.new;
  return (
    <div className="flex items-center gap-2 mt-6 mb-2">
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.dot}`} />
      <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</span>
      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${s.badge}`}>{count}</span>
    </div>
  );
}

export default SectionHeader;
