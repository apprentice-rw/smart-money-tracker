export const BRAND_OVERRIDES = {
  // Amazon
  'AMAZON.COM INC': 'Amazon',
  'AMAZON COM INC': 'Amazon',
  // Alphabet
  'ALPHABET INC-CL A': 'Alphabet',
  'ALPHABET INC-CL C': 'Alphabet',
  // Meta
  'META PLATFORMS INC-CLASS A': 'Meta',
  'META PLATFORMS INC': 'Meta',
  // AppLovin
  'APPLOVIN CORP-CLASS A': 'AppLovin',
  'APPLOVIN CORP': 'AppLovin',
  // Berkshire Hathaway
  'BERKSHIRE HATHAWAY INC-CL B': 'Berkshire Hathaway',
  'BERKSHIRE HATHAWAY INC-CL A': 'Berkshire Hathaway',
  // DoorDash
  'DOORDASH INC - A': 'DoorDash',
  'DOORDASH INC-CLASS A': 'DoorDash',
  // Other class-share / ADR edge cases
  'SPOTIFY TECHNOLOGY S A': 'Spotify',
  'TAIWAN SEMICONDUCTOR-SP ADR': 'TSMC',
  'UBER TECHNOLOGIES INC': 'Uber',
  'AIRBNB INC-CLASS A': 'Airbnb',
  'COINBASE GLOBAL INC-CLASS A': 'Coinbase',
  'PINTEREST INC- CLASS A': 'Pinterest',
  'SNAP INC-CLASS A': 'Snap',
  'LYFT INC-CLASS A': 'Lyft',
  // S&P 500 ETF
  'SPDR S&P 500 ETF TRUST-US': 'SPY ETF',
  'SS SPDR S&P 500 ETF TRUST-US': 'SPY ETF',
  // Plain names that title-case fine but are worth pinning
  'BROOKFIELD CORP': 'Brookfield',
  'VISTRA CORP': 'Vistra',
  'COUPANG INC': 'Coupang',
  'BROADCOM INC': 'Broadcom',
  'NVIDIA CORP': 'Nvidia',
  'MICROSOFT CORP': 'Microsoft',
  // Ticker-as-name overrides
  'ITT INC': 'ITT',
  'CRH PLC': 'CRH',
  'ASML HOLDING NV': 'ASML',
  'ASML HOLDING N V': 'ASML',
  'ASML HOLDING': 'ASML',
  // Legacy abbreviation overrides
  'FINL': 'Finish Line',
  'HLDG': 'Holdings',
  'MTR': 'Motors',
};

export const UPPERCASE_WORDS = new Set(['AI', 'ETF', 'LP', 'LLP', 'USA', 'US', 'UK', 'EU', 'IPO', 'REIT', 'S&P', 'IT', 'TV', 'HR', 'PR', 'ITT']);

export function simplifyName(str) {
  if (!str) return '';
  const upper = str.toUpperCase().trim();
  if (BRAND_OVERRIDES[upper]) return BRAND_OVERRIDES[upper];
  let name = str.trim();
  // Strip share-class suffixes: -Class A/B/C, -CL A/B/C
  name = name.replace(/\s*-\s*CLASS\s+[A-C]\b/gi, '');
  name = name.replace(/\s*-\s*CL\s+[A-C]\b/gi, '');
  // Strip ADR suffixes: -SP ADR, - ADR
  name = name.replace(/\s*-\s*SP\s+ADR\b/gi, '').replace(/\s*-\s*ADR\b/gi, '');
  // Strip trailing standalone class letter: " - A" / "- A" at end of string
  name = name.replace(/\s*-\s*[A-C]\s*$/gi, '');
  // Remove .COM from domain-style names (e.g. AMAZON.COM)
  name = name.replace(/\.COM\b/gi, '');
  // Title-case while preserving known acronyms
  name = name.replace(/\b(\w+)\b/g, (word) => {
    const up = word.toUpperCase();
    if (UPPERCASE_WORDS.has(up)) return up;
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  });
  // Strip safe legal suffixes
  name = name.replace(/\s+(Inc|Corp|Corporation|Ltd|LLC|PLC)\.?$/i, '').trim();
  // Clean trailing punctuation and whitespace
  name = name.replace(/[,\.\-\s]+$/, '').trim();
  return name;
}

export function displayName(item, tickerMap) {
  const entry = tickerMap?.[item.cusip];
  if (entry?.name) return simplifyName(entry.name);
  return simplifyName(item.issuer_name);
}
