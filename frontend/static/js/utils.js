export function fmt(n) {
  return Math.round(n).toLocaleString('uk-UA');
}

export function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function fmtDate(iso) {
  return iso ? iso.slice(0, 10) : '—';
}
