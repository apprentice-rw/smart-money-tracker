
export default function StatsBar({ changes, holdingsData }) {
  if (!changes) return null;
  const { summary } = changes;

  // Total current positions = everything except closed
  const totalPositions = (summary.new || 0) + (summary.increased || 0)
                       + (summary.decreased || 0) + (summary.unchanged || 0);

  // Turnover = (new + closed) / total current positions
  const turnover = totalPositions > 0
    ? (((summary.new || 0) + (summary.closed || 0)) / totalPositions * 100).toFixed(1)
    : '—';

  // Top-5 concentration from eagerly-loaded holdings
  let top5Pct = null;
  if (holdingsData && holdingsData.total_value > 0) {
    const top5Val = holdingsData.holdings
      .slice(0, 5)
      .reduce((s, h) => s + (h.value || 0), 0);
    top5Pct = (top5Val / holdingsData.total_value * 100).toFixed(1);
  }

  return (
    <div className="flex items-center gap-2.5 mt-1.5 flex-wrap"
         style={{ fontVariantNumeric: 'tabular-nums' }}>
      <span className="text-[11px] text-gray-400">
        <span className="font-semibold text-gray-600">{totalPositions}</span> pos
      </span>
      <span className="text-gray-200 text-[10px]">·</span>
      <span className="text-[11px] text-gray-400">
        <span className="font-semibold text-gray-600">{turnover}%</span> turnover
      </span>
      <span className="text-gray-200 text-[10px]">·</span>
      <span className="text-[11px] text-gray-400">
        {top5Pct !== null
          ? <><span className="font-semibold text-gray-600">{top5Pct}%</span> top-5</>
          : <span className="text-gray-300">top-5 …</span>}
      </span>
    </div>
  );
}
