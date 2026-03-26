
export const QEND_PRICE_TIP =
  "This is the stock\u2019s market price at quarter-end, not the institution\u2019s " +
  "actual cost basis. True cost basis cannot be determined from 13F filings alone.";

export function InfoTooltip({ text }) {
  return (
    <span className="relative group inline-flex items-center ml-0.5">
      <span className="text-gray-300 hover:text-gray-500 cursor-help select-none text-[10px]"
            onClick={(e) => e.stopPropagation()}>ⓘ</span>
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2
                       w-52 px-2.5 py-2 rounded-lg bg-gray-800 text-white text-[11px] leading-snug
                       opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50
                       shadow-xl whitespace-normal text-left">
        {text}
      </span>
    </span>
  );
}

export default InfoTooltip;
