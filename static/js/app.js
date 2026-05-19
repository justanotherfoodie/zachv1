/**
 * GlassPy — global JS utilities
 */

// ── API helper ──────────────────────────────────────────────────────────────
const API = {
  async post(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.json();
  },
  async get(url) {
    const res = await fetch(url);
    return res.json();
  },
};

// ── Debounce ────────────────────────────────────────────────────────────────
function debounce(fn, ms = 300) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

// ── Number formatting ───────────────────────────────────────────────────────
function fmt(v, decimals = 3) {
  if (v == null || isNaN(v)) return '—';
  return parseFloat(v).toFixed(decimals);
}

// ── Plotly dark theme defaults ───────────────────────────────────────────────
const PLOT_DEFAULTS = {
  paper_bgcolor: 'transparent',
  plot_bgcolor:  'rgba(255,255,255,0.04)',
  font:          { color: 'hsl(var(--bc))', size: 11 },
  grid:          { color: 'rgba(255,255,255,0.06)' },
};

// ── Toast notifications ──────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `alert alert-${type} fixed bottom-6 right-6 z-50 max-w-sm shadow-xl text-sm`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ── Copy-to-clipboard ────────────────────────────────────────────────────────
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => toast('Copied!', 'success'));
}

// ── Property name display ────────────────────────────────────────────────────
function prettyProp(name) {
  return (name || '').replace(/_/g, ' ');
}

// ── Oxide colour palette (for charts) ────────────────────────────────────────
const OXIDE_COLORS = {
  SiO2:   '#6366f1', B2O3:   '#8b5cf6', Al2O3:  '#a78bfa',
  Na2O:   '#f59e0b', K2O:    '#f97316', Li2O:   '#fbbf24',
  CaO:    '#10b981', MgO:    '#34d399', BaO:    '#6ee7b7',
  TiO2:   '#3b82f6', ZrO2:   '#60a5fa', La2O3:  '#93c5fd',
  Fe2O3:  '#ef4444', Nb2O5:  '#f87171', V2O5:   '#fca5a5',
  PbO:    '#6b7280', ZnO:    '#9ca3af', P2O5:   '#d1d5db',
};
function oxideColor(oxide) {
  return OXIDE_COLORS[oxide] || '#94a3b8';
}
