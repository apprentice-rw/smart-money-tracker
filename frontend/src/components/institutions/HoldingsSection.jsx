import { useState, useContext } from 'react';
import { TickerCtx } from '../../contexts/TickerContext.js';
import { StockDrawerCtx } from '../../contexts/DrawerContext.js';
import { fmtVal, fmtShares, fmtPrice, fmtPeriod } from '../../utils/formatters.js';
import { InfoTooltip, QEND_PRICE_TIP } from '../common/InfoTooltip.jsx';
import ChevronIcon from '../common/ChevronIcon.jsx';
import Spinner from '../common/Spinner.jsx';

export default function HoldingsSection({ data, loading, error }) {
  const tickerMap  = useContext(TickerCtx);
  const openDrawer = useContext(StockDrawerCtx);
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-5 pt-4 border-t border-gray-100">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800 font-medium transition-colors"
      >
        <ChevronIcon open={open} />
        <span>Full Holdings</span>
        {data && (
          <span className="text-xs text-gray-400 font-normal">
            {data.total_positions} positions · {fmtVal(data.total_value)}
          </span>
        )}
      </button>

      {open && (
        <div className="mt-3">
          {loading && <Spinner small />}
          {error && <p className="text-sm text-red-400 py-2">{error}</p>}
          {data && !loading && (
            <>
              <p className="text-xs text-gray-400 mb-3" style={{ fontVariantNumeric: 'tabular-nums' }}>
                {data.total_positions} positions · {fmtVal(data.total_value)} total value · {fmtPeriod(data.period_of_report)}
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="pb-2 pr-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right w-7">#</th>
                      <th className="pb-2 pr-4 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Issuer</th>
                      <th className="pb-2 pr-4 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right">Shares</th>
                      <th className="pb-2 pr-4 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right">Weight</th>
                      <th className="pb-2 pr-4 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right">
                        <span className="inline-flex items-center justify-end gap-0.5">
                          Q-end Price <InfoTooltip text={QEND_PRICE_TIP} />
                        </span>
                      </th>
                      <th className="pb-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider text-right">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.holdings.map((h) => {
                      const ticker = tickerMap ? tickerMap.get(h.cusip)?.ticker : null;
                      const weight = data.total_value > 0
                        ? (h.value / data.total_value * 100).toFixed(1) + '%'
                        : '—';
                      return (
                        <tr
                          key={h.cusip}
                          className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors cursor-pointer"
                          onClick={() => openDrawer?.(h.cusip, h.issuer_name)}
                        >
                          <td className="py-2 pr-2 text-xs text-gray-400 text-right"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{h.rank}</td>
                          <td className="py-2 pr-4">
                            <span className="text-sm text-gray-900" title={h.issuer_name}>
                              {ticker || (h.issuer_name.length > 15 ? h.issuer_name.slice(0, 15) + '…' : h.issuer_name)}
                            </span>
                            <code className="ml-2 text-[11px] text-gray-400 hidden sm:inline">{h.cusip}</code>
                          </td>
                          <td className="py-2 pr-4 text-sm text-right text-gray-600"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtShares(h.shares)}</td>
                          <td className="py-2 pr-4 text-sm text-right text-gray-500"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{weight}</td>
                          <td className="py-2 pr-4 text-sm text-right text-gray-500"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(h.value, h.shares)}</td>
                          <td className="py-2 text-sm text-right font-semibold text-gray-800"
                              style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtVal(h.value)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
