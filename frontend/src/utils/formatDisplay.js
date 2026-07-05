/** Safe values for React text nodes — never render raw objects. */

function isRenderableObject(value) {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

export function formatPowerState(value) {
  if (value == null || value === '') return 'Unknown';
  if (isRenderableObject(value)) {
    const code = value.code ?? value.name ?? value.state;
    if (code != null && code !== '') return formatPowerState(code);
    return 'Unknown';
  }
  const text = String(value).trim();
  if (!text || text === '[object Object]') return 'Unknown';
  if (text.includes('/')) return text.split('/').pop() || text;
  return text;
}

export function toDisplayNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function toDisplayText(value) {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    return value.length ? value.map((v) => toDisplayText(v)).join(', ') : '—';
  }
  if (typeof value === 'object') {
    const name = value.name ?? value.code ?? value.displayName ?? value.tier;
    if (name != null && name !== '') return toDisplayText(name);
    const keys = Object.keys(value);
    if (!keys.length) return '—';
    return keys
      .slice(0, 3)
      .map((k) => `${k}: ${toDisplayText(value[k])}`)
      .join(', ');
  }
  return String(value);
}
