import { fmtVal, fmtShares, fmtPeriod } from '../../utils/formatters.js';

export default function ChartTooltip({ active, payload, label, mode }) {
  if (!active || !payload?.length) return null;
  const visible = payload.filter((p) => p.value != null);
  if (!visible.length) return null;
  return (
    <div className="bg-white border border-gray-100 rounded-xl shadow-lg px-3 py-2.5 text-xs">
      <p className="font-semibold text-gray-700 mb-1">{fmtPeriod(label)}</p>
      {visible.map((p) => {
        const isClosed = mode === 'qoq' ? p.value === -100 : p.value === 0;
        const fmtValue = isClosed
          ? 'Closed'
          : (mode === 'value' || mode === 'log')
            ? fmtVal(p.value)
            : mode === 'shares'
              ? fmtShares(p.value)
              : mode === 'qoq'
                ? (p.value >= 0 ? '+' : '') + p.value.toFixed(1) + '%'
                : p.value.toFixed(2) + '%';
        return (
          <div key={p.dataKey} className="flex items-center gap-2 py-0.5">
            <span className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: isClosed ? '#ef4444' : p.color }} />
            <span className="text-gray-600">{p.name}:</span>
            <span className={`font-semibold ${isClosed ? 'text-red-500' : 'text-gray-900'}`}>
              {fmtValue}
            </span>
          </div>
        );
      })}
    </div>
  );
}
