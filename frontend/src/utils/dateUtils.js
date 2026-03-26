export function periodRange(periodEnd) {
  const d = new Date(periodEnd + 'T00:00:00');
  const qStart = new Date(d.getFullYear(), d.getMonth() - 2, 1);
  const fmt = (dt) => dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  return `${fmt(qStart)} – ${fmt(d)}, ${d.getFullYear()}`;
}

export function fmtFilingDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}
