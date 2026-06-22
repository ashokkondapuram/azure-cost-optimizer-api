/**
 * Generic resource list page.
 * Used for all resource types that don't have a dedicated page.
 * Reads from the DB via the backend REST API.
 */
import React, { useContext, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, RefreshCw, Search } from 'lucide-react';
import { AppCtx } from '../App';
import api from '../api/client';

export default function ResourceList({ title, apiPath }) {
  const { subscription } = useContext(AppCtx);
  const [search, setSearch] = useState('');

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: [apiPath, subscription],
    queryFn: () =>
      api.get(apiPath, { params: { subscription_id: subscription } }).then(r => {
        const d = r.data;
        // Handle both array and { value: [] } shapes
        return Array.isArray(d) ? d : (d?.value || []);
      }),
    enabled: !!subscription,
    staleTime: 5 * 60_000,
  });

  const rows = (data || []).filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (r.name || r.resource_name || '').toLowerCase().includes(q) ||
      (r.resourceGroup || r.resource_group || '').toLowerCase().includes(q) ||
      (r.location || '').toLowerCase().includes(q) ||
      (r.sku || '').toLowerCase().includes(q)
    );
  });

  // Derive columns dynamically from first row
  const firstRow = rows[0] || {};
  const PRIORITY_COLS = ['name', 'resource_name', 'resourceGroup', 'resource_group', 'location', 'sku', 'state', 'monthlyCostUsd', 'syncedAt'];
  const SKIP_COLS = new Set(['id', 'type', 'resource_id', 'tags', 'properties', 'tags_json', 'properties_json']);
  const cols = [
    ...PRIORITY_COLS.filter(k => k in firstRow),
    ...Object.keys(firstRow).filter(k => !PRIORITY_COLS.includes(k) && !SKIP_COLS.has(k)),
  ].slice(0, 8);

  const fmt = (val) => {
    if (val == null) return <span style={{ opacity: 0.35 }}>—</span>;
    if (typeof val === 'number') return val.toLocaleString();
    if (typeof val === 'boolean') return val ? 'Yes' : 'No';
    if (typeof val === 'string' && val.length > 60) return val.slice(0, 58) + '…';
    return String(val);
  };

  const colLabel = (k) =>
    k.replace(/([A-Z])/g, ' $1')
     .replace(/_/g, ' ')
     .replace(/^./, c => c.toUpperCase())
     .trim();

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">{title}</div>
          <div className="page-sub">
            {subscription
              ? `${rows.length} resource${rows.length !== 1 ? 's' : ''} · from database · ${subscription}`
              : 'No subscription selected'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <div style={{ position: 'relative' }}>
            <Search size={13} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', opacity: 0.4 }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter…"
              style={{ paddingLeft: 28, fontSize: '0.8rem', width: 180 }}
            />
          </div>
          <button className="btn btn-secondary" onClick={refetch} disabled={isFetching}>
            <RefreshCw size={13} className={isFetching ? 'spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {!subscription && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
          <AlertTriangle size={28} style={{ margin: '0 auto 1rem', display: 'block', opacity: 0.4 }} />
          <p>Select a subscription from the sidebar.</p>
        </div>
      )}

      {subscription && isLoading && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
          <div className="spin" style={{ width: 24, height: 24, margin: '0 auto 1rem' }} />
          <p style={{ fontSize: '0.85rem' }}>Loading from database…</p>
        </div>
      )}

      {subscription && isError && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--danger)' }}>
          <AlertTriangle size={28} style={{ margin: '0 auto 1rem', display: 'block' }} />
          <p style={{ fontSize: '0.85rem' }}>Failed to load. Make sure the backend is running and data has been synced.</p>
          <button className="btn btn-secondary" style={{ marginTop: '1rem' }} onClick={refetch}>Retry</button>
        </div>
      )}

      {subscription && !isLoading && !isError && rows.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
          <AlertTriangle size={28} style={{ margin: '0 auto 1rem', display: 'block', opacity: 0.4 }} />
          <p style={{ fontSize: '0.85rem' }}>
            {search ? 'No results match your filter.' : 'No data yet — run a sync first.'}
          </p>
          {!search && (
            <code style={{ fontSize: '0.78rem', background: 'var(--bg2)', padding: '4px 10px', borderRadius: 6 }}>
              POST /api/resources/sync?subscription_id={subscription}
            </code>
          )}
        </div>
      )}

      {subscription && !isLoading && rows.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  {cols.map(k => <th key={k}>{colLabel(k)}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={row.id || row.resource_id || i}>
                    {cols.map(k => (
                      <td key={k}>
                        {k === 'state' ? (
                          <span className={`badge ${
                            /running|active|enabled|succeeded/i.test(row[k]) ? 'badge-success' :
                            /stopped|deallocated|disabled/i.test(row[k])    ? 'badge-danger'  :
                            'badge-warning'
                          }`}>
                            {row[k]}
                          </span>
                        ) : fmt(row[k])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ padding: '0.65rem 1.25rem', borderTop: '1px solid var(--border)', fontSize: '0.75rem', color: 'var(--text3)' }}>
            {rows.length} record{rows.length !== 1 ? 's' : ''}
            {search && ` (filtered from ${data.length})`}
          </div>
        </div>
      )}
    </div>
  );
}
