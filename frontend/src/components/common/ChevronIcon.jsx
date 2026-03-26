
function ChevronIcon({ open }) {
  return (
    <svg
      className={`w-3.5 h-3.5 text-gray-400 flex-shrink-0 chevron ${open ? 'open' : ''}`}
      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}

export default ChevronIcon;
