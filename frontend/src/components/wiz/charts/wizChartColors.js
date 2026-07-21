export const CHART_AXIS_TICK = { fill: 'var(--chart-axis)', fontSize: 10 };
export const CHART_GRID = { strokeDasharray: '3 3', stroke: 'var(--chart-grid)' };
export const CHART_TOOLTIP_STYLE = {
  background: 'var(--chart-tooltip-bg)',
  border: '1px solid var(--chart-tooltip-border)',
  borderRadius: 10,
  color: 'var(--text)',
};

export const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

export const SEVERITY_COLORS = {
  CRITICAL: 'var(--danger)',
  HIGH: '#f97316',
  MEDIUM: 'var(--warning)',
  LOW: 'var(--success)',
  INFO: 'var(--zafin-cyan)',
};

/** Solid fills for SVG charts and legend swatches (CSS variables are unreliable in SVG gradients). */
export const SEVERITY_FILL = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#22c55e',
  INFO: '#009cff',
};

export const SEVERITY_GRADIENTS = {
  CRITICAL: ['#fca5a5', '#ef4444'],
  HIGH: ['#fdba74', '#f97316'],
  MEDIUM: ['#fde047', '#eab308'],
  LOW: ['#86efac', '#22c55e'],
  INFO: ['#7dd3fc', '#009cff'],
};

export const CHART_PALETTE = [
  'var(--chart-series-1)',
  'var(--chart-series-4)',
  'var(--chart-series-2)',
  'var(--chart-series-5)',
  '#ec4899',
  'var(--chart-series-3)',
  '#14b8a6',
  '#6366f1',
];

export function darken(hex, amount = 0.25) {
  const n = hex.replace('#', '');
  const r = Math.max(0, parseInt(n.slice(0, 2), 16) * (1 - amount));
  const g = Math.max(0, parseInt(n.slice(2, 4), 16) * (1 - amount));
  const b = Math.max(0, parseInt(n.slice(4, 6), 16) * (1 - amount));
  return `rgb(${r | 0},${g | 0},${b | 0})`;
}
