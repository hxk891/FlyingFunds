// format a percentage, with optional sign prefix
// fmtPct(3.5) '+3.5%'
// fmtPct(-1.2) '-1.2%'
// fmtPct(0, 2) '+0.00%'
function fmtPct(v, decimals, showSign) {
  if (v == null || isNaN(v)) return '—';
  const d  = decimals != null ? decimals : 1;
  const sg = showSign !== false; // default true
  const n  = Number(v).toFixed(d);
  return (sg && v >= 0 ? '+' : '') + n + '%';
}

// format a signed change value £+12.34 or £-5.00
function fmtSignedGBP(v, decimals) {
  if (v == null || isNaN(v)) return '—';
  const d   = decimals != null ? decimals : 2;
  const abs = Math.abs(Number(v)).toFixed(d);
  return (v >= 0 ? '+' : '-') + '£' + abs;
}

// format a GBP value e.g. £1,234 or £1,234.56
function fmtGBP(v, decimals) {
  if (v == null || isNaN(v)) return '—';
  const d = decimals != null ? decimals : 0;
  return '£' + Number(v).toLocaleString('en-GB', {
    minimumFractionDigits: d,
    maximumFractionDigits: d
  });
}

// positive/negative css class name
function chgClass(v) {
  return Number(v) >= 0 ? 'positive' : 'negative';
}

// format a GBP price with exactly 2 decimals for stock prices etc
function fmtPrice(v) {
  if (v == null || isNaN(v)) return '—';
  return '£' + Number(v).toFixed(2);
}
