export function sortItems(items, sortKey, type) {
  if (!items || items.length === 0) return items;
  const getValue  = (it) => (type === 'closed' ? it.prev_value  : it.curr_value)  || 0;
  const getShares = (it) => (type === 'closed' ? it.prev_shares : it.curr_shares) || 0;
  const arr = [...items];
  switch (sortKey) {
    case 'value_asc':   return arr.sort((a, b) => getValue(a)        - getValue(b));
    case 'pct_desc':    return arr.sort((a, b) => (b.shares_pct||0) - (a.shares_pct||0));
    case 'pct_asc':     return arr.sort((a, b) => (a.shares_pct||0) - (b.shares_pct||0));
    case 'shares_desc': return arr.sort((a, b) => getShares(b)      - getShares(a));
    case 'shares_asc':  return arr.sort((a, b) => getShares(a)      - getShares(b));
    default:            return arr.sort((a, b) => getValue(b)        - getValue(a)); // value_desc
  }
}

export function avgWeight(items, valueKey, totalKey) {
  if (!items || !items.length) return 0;
  const sum = items.reduce((acc, h) => {
    const total = h[totalKey] || 0;
    return acc + (total > 0 ? (h[valueKey] || 0) / total : 0);
  }, 0);
  return sum / items.length;
}
