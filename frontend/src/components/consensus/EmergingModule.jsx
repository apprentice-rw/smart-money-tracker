import { useState, useMemo } from 'react';
import { fmtVal, fmtPeriod } from '../../utils/formatters.js';
import { displayName } from '../../utils/nameUtils.js';
import SortPills from '../common/SortPills.jsx';
import ModuleCard from '../common/ModuleCard.jsx';
import ShowMoreTable from '../common/ShowMoreTable.jsx';
import ModuleSpinner from './ModuleSpinner.jsx';

const EMERGING_SORT_OPTS = [
  { key: 'holder_delta', label: 'Institutions' },
  { key: 'total_value',  label: 'Total Value' },
];

export default function EmergingModule({ data, onStockClick, tickerMap, collapsed, onCollapseToggle }) {
  const [sortKey, setSortKey] = useState('holder_delta');
  const [sortDir, setSortDir] = useState('desc');

  const sorted = useMemo(() => {
    if (!data?.results) return [];
    return [...data.results].sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      return sortDir === 'desc' ? bv - av : av - bv;
    });
  }, [data, sortKey, sortDir]);

  if (!data) return <ModuleCard title="Emerging Consensus" subtitle="Loading..." onCollapseToggle={onCollapseToggle} collapsed={collapsed}><ModuleSpinner /></ModuleCard>;
  return (
    <ModuleCard
      title="Emerging Consensus"
      subtitle={data.prev_period ? `Holder count growing vs ${fmtPeriod(data.prev_period)}` : 'Growing institutional interest'}
      collapsed={collapsed}
      onCollapseToggle={onCollapseToggle}
    >
      <SortPills
        options={EMERGING_SORT_OPTS}
        sortKey={sortKey}
        sortDir={sortDir}
        onChange={(k, d) => { setSortKey(k); setSortDir(d); }}
      />
      <ShowMoreTable
        items={sorted}
        emptyMsg="No emerging consensus found (requires prior quarter data)"
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
            </td>
            <td className="py-2 pl-2 text-right align-top whitespace-nowrap">
              <div className="font-medium text-green-600">+{item.holder_delta} holders</div>
              <div className="text-gray-400">{item.prev_holders} → {item.curr_holders}</div>
              <div className="text-gray-500">{fmtVal(item.total_value)}</div>
            </td>
          </tr>
        )}
      />
    </ModuleCard>
  );
}
