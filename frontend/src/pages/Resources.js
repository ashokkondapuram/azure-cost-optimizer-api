import React, { useState } from 'react';
import {
  fetchAllResources, fetchVMs, fetchAKS, fetchStorage,
  fetchAppServices, fetchSQL, fetchDisks, fetchKeyVaults, fetchPublicIPs
} from '../api/client';

const TABS = [
  { key: 'all', label: 'All Resources', fn: fetchAllResources },
  { key: 'vms', label: 'Virtual Machines', fn: fetchVMs },
  { key: 'aks', label: 'AKS Clusters', fn: fetchAKS },
  { key: 'storage', label: 'Storage', fn: fetchStorage },
  { key: 'app', label: 'App Services', fn: fetchAppServices },
  { key: 'sql', label: 'SQL Servers', fn: fetchSQL },
  { key: 'disks', label: 'Disks', fn: fetchDisks },
  { key: 'kv', label: 'Key Vaults', fn: fetchKeyVaults },
  { key: 'pip', label: 'Public IPs', fn: fetchPublicIPs },
];

export default function Resources({ subscriptionId }) {
  const [tab, setTab] = useState('all');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async (key) => {
    const t = TABS.find(t => t.key === key);
    if (!subscriptionId) return setError('Enter a Subscription ID in the sidebar.');
    setTab(key); setLoading(true); setError('');
    try {
      const res = await t.fn(subscriptionId);
      setItems(res.data || []);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        {TABS.map(t => (
          <button key={t.key}
            onClick={() => load(t.key)}
            style={{ background: tab === t.key ? '#005fa3' : '#0078d4' }}>
            {t.label}
          </button>
        ))}
      </div>
      {loading && <p className="loading">Loading...</p>}
      {error && <p className="error">{error}</p>}
      {items.length > 0 && (
        <div className="card">
          <h2>{TABS.find(t => t.key === tab)?.label} ({items.length})</h2>
          <table>
            <thead><tr><th>Name</th><th>Type</th><th>Location</th><th>Resource Group</th></tr></thead>
            <tbody>
              {items.map((item, i) => (
                <tr key={i}>
                  <td>{item.name}</td>
                  <td><span className="tag">{item.type?.split('/').pop()}</span></td>
                  <td>{item.location}</td>
                  <td>{item.id?.split('/resourceGroups/')[1]?.split('/')[0] || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
