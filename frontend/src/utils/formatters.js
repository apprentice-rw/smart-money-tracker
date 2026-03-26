export function fmtVal(v) {
  if (v == null) return '—';
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v}`;
}

export function fmtShares(n) {
  if (n == null) return '—';
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return `${n}`;
}

export function fmtPct(p) {
  if (p == null) return '';
  return `${p >= 0 ? '+' : ''}${p.toFixed(1)}%`;
}

export function fmtPeriod(s) {
  if (!s) return '';
  const [year, month] = s.split('-');
  return `Q${Math.ceil(parseInt(month, 10) / 3)} ${year}`;
}

export function fmtPrice(value, shares) {
  if (!value || !shares || shares === 0) return '—';
  return `$${(value / shares).toFixed(2)}`;
}

export function truncate(str, max) {
  return str.length <= max ? str : str.slice(0, max - 1).trimEnd() + '…';
}
