/**
 * Export Center — client-side CSV/JSON export helpers.
 * Data is fetched from existing cost endpoints then serialised locally.
 * No dedicated server endpoint needed — the backend already returns
 * structured JSON that we transform here.
 */

export function toCsv(rows, columns) {
  if (!rows?.length) return '';
  const cols = columns ?? Object.keys(rows[0]);
  const escape = (v) => {
    const s = v == null ? '' : String(v);
    return s.includes(',') || s.includes('"') || s.includes('\n')
      ? `"${s.replace(/"/g, '""')}"`
      : s;
  };
  const header = cols.map(escape).join(',');
  const body = rows.map((r) => cols.map((c) => escape(r[c])).join(',')).join('\n');
  return `${header}\n${body}`;
}

export function downloadCsv(filename, csv) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

/**
 * Fetch and export cost-by-service as CSV.
 * Accepts pre-fetched data so the ExportCenter page can pass in
 * data already loaded from any cost panel.
 */
export function exportServiceCostCsv(data, filename) {
  const rows = (data?.properties?.rows ?? []).map((r) => {
    const cols = data?.properties?.columns ?? [];
    return Object.fromEntries(cols.map((c, i) => [c.name ?? c, r[i]]));
  });
  downloadCsv(filename ?? `cost-by-service-${new Date().toISOString().slice(0,10)}.csv`, toCsv(rows));
}
