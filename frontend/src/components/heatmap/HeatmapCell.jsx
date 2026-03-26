import { useContext } from 'react';
import { HeatmapTooltipCtx } from '../../contexts/HeatmapTooltipContext.js';
import { HEATMAP_COLORS, HEATMAP_TEXT } from '../../constants/heatmap.js';
import { truncate } from '../../utils/formatters.js';

// Custom SVG cell renderer for Recharts Treemap.
// Recharts clones this element with treemap node props; all data fields are available.
// Uses HeatmapTooltipCtx to communicate hover state to the parent HeatmapRow.
function HeatmapCell(props) {
  const { x, y, width, height, depth, name, changeType, sharesPct } = props;
  const setTooltip = useContext(HeatmapTooltipCtx);

  // depth 0 = root (invisible bounding box); skip it and zero-size cells
  if (depth !== 1 || !width || !height || width < 2 || height < 2) return null;

  const fill     = HEATMAP_COLORS[changeType] || HEATMAP_COLORS.unchanged;
  const textFill = HEATMAP_TEXT[changeType]   || HEATMAP_TEXT.unchanged;

  const fontSize    = Math.min(width / 6, height / 2.5, 14);
  const fontSizePct = Math.max(fontSize - 1.5, 7);
  const showName    = fontSize >= 8;
  const showPct     = showName && fontSizePct >= 7 && sharesPct != null && height > 34;

  // Word-wrap the name into 1 or 2 lines, truncating with ellipsis if needed
  const pxPerChar = fontSize * 0.6; // ~0.6em per character
  const maxChars  = Math.max(1, Math.floor(width / pxPerChar) - 1);

  let line1 = '', line2 = '';
  if (showName) {
    const words   = name.split(' ');
    const twoLine = height > 40;
    let   built   = '';
    let   splitAt = -1; // index of first word that overflows line 1

    for (let i = 0; i < words.length; i++) {
      const attempt = built ? built + ' ' + words[i] : words[i];
      if (attempt.length <= maxChars) {
        built = attempt;
      } else {
        splitAt = i;
        break;
      }
    }

    if (splitAt === -1) {
      // Everything fits on one line
      line1 = built;
    } else if (twoLine) {
      line1 = built || truncate(words[0], maxChars); // at least one word on line 1
      const rest = words.slice(splitAt).join(' ');
      line2 = truncate(rest, maxChars);
    } else {
      // Single-line with truncation
      line1 = truncate(built || words[0], maxChars);
    }
  }

  const twoLines   = line2 !== '';
  const lineGap    = fontSize * 1.15;
  // Total text block height: 1 or 2 name lines + optional pct line
  const textBlockH = (twoLines ? lineGap * 2 : lineGap) + (showPct ? lineGap * 0.9 : 0);
  const textTop    = y + height / 2 - textBlockH / 2 + lineGap / 2;

  return (
    <g
      onMouseEnter={(e) => setTooltip?.({ x: e.clientX, y: e.clientY, node: props })}
      onMouseLeave={() => setTooltip?.(null)}
      style={{ cursor: 'default' }}
    >
      <rect x={x + 1} y={y + 1} width={width - 2} height={height - 2} fill={fill} rx={2} />
      {showName && (
        <>
          <text
            x={x + width / 2} y={textTop}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={fontSize} fontWeight={600} fill={textFill}
            style={{ pointerEvents: 'none', userSelect: 'none' }}
          >
            {line1}
          </text>
          {twoLines && (
            <text
              x={x + width / 2} y={textTop + lineGap}
              textAnchor="middle" dominantBaseline="middle"
              fontSize={fontSize} fontWeight={600} fill={textFill}
              style={{ pointerEvents: 'none', userSelect: 'none' }}
            >
              {line2}
            </text>
          )}
        </>
      )}
      {showPct && (
        <text
          x={x + width / 2} y={textTop + (twoLines ? lineGap * 2 : lineGap)}
          textAnchor="middle" dominantBaseline="middle"
          fontSize={fontSizePct} fill={textFill} opacity={0.75}
          style={{ pointerEvents: 'none', userSelect: 'none' }}
        >
          {sharesPct > 0 ? '+' : ''}{sharesPct.toFixed(0)}%
        </text>
      )}
    </g>
  );
}

export default HeatmapCell;
