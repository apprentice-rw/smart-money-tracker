import { useState, useMemo } from 'react';
import { fmtVal } from '../../utils/formatters.js';
import { displayName } from '../../utils/nameUtils.js';
import { avgWeight } from '../../utils/sortUtils.js';
import SortPills from '../common/SortPills.jsx';
import ModuleCard from '../common/ModuleCard.jsx';
import ShowMoreTable from '../common/ShowMoreTable.jsx';
import HolderBadges from './HolderBadges.jsx';
import ModuleSpinner from './ModuleSpinner.jsx';

const HOLDINGS_SORT_OPTS = [
  { key: 'holder_count', label: 'Institutions' },
  { key: 'total_value',  label: 'Total Value' },
  { key: 'avg_weight',   label: 'Avg Weight' },
];

export default function HoldingsModule({ data, onStockClick, tickerMap, collapsed, onCollapseToggle }) {
  const [sortKey, setSortKey] = useState('holder_count');
  const [sortDir, setSortDir] = useState('desc');

  const sorted = useMemo(() => {
    if (!data?.results) return [];
    return [...data.results].sort((a, b) => {
      const av = sortKey === 'avg_weight'
        ? avgWeight(a.holders, 'value', 'institution_total_value')
        : (a[sortKey] ?? 0);
      const bv = sortKey === 'avg_weight'
        ? avgWeight(b.holders, 'value', 'institution_total_value')
        : (b[sortKey] ?? 0);
      return sortDir === 'desc' ? bv - av : av - bv;
    });
  }, [data, sortKey, sortDir]);

  if (!data) return <ModuleSpinner />;
  return (
    <ModuleCard
      title="Top Consensus Holdings"
      subtitle="Stocks held by the most institutions"
      collapsed={collapsed}
      onCollapseToggle={onCollapseToggle}
    >
      <SortPills
        options={HOLDINGS_SORT_OPTS}
        sortKey={sortKey}
        sortDir={sortDir}
        onChange={(k, d) => { setSortKey(k); setSortDir(d); }}
      />
      <ShowMoreTable
        items={sorted}
        emptyMsg="No consensus holdings found"
        renderRow={(item, i) => (
          <tr
            key={item.cusip}
            onClick={() => onStockClick(item.cusip, item.issuer_name)}
            className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
          >
            <td className="py-2 pr-3 text-gray-400 w-6 align-top">{i + 1}</td>
            <td className="py-2 pr-3 align-top">
              <div>
                {tickerMap?.[item.cusip]?.ticker ? (
                  <>
                    <span className="text-gray-900 font-semibold text-sm">{tickerMap[item.cusip].ticker}</span>
                    <span className="text-gray-400 text-xs ml-1.5">{displayName(item, tickerMap)}</span>
                  </>
                ) : (
                  <>
                    <span className="text-gray-900 font-semibold text-sm">{displayName(item, tickerMap)}</span>
                    <span className="text-gray-400 text-xs ml-1.5">{item.issuer_name}</span>
                  </>
                )}
              </div>
              <HolderBadges holders={item.holders} />
            </td>
            <td className="py-2 pl-2 text-right align-top whitespace-nowrap">
              <div className="font-medium text-gray-900">{fmtVal(item.total_value)}</div>
              <div className="text-gray-400">{item.holder_count} holders</div>
            </td>
          </tr>
        )}
      />
    </ModuleCard>
  );
}
