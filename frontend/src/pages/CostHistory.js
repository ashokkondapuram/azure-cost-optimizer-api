import React, { useEffect, useState } from 'react';
import { fetchCostHistory } from '../api/client';

export default function CostHistory() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchCostHistory()
      .then(r => setRecords(r.data || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="loading">Loading cost history...</p>;
  if (error) return <p className="error">{error}</p>;

  return (
    <div className="card">
      <h2>Cost Query History ({records.length})</h2>
      <table>
        <thead>
          <tr><th>ID</th><th>Subscription</th><th>Resource Group</th><th>Timeframe</th><th>Queried At</th></tr>
        </thead>
        <tbody>
          {records.map((r, i) => (
            <tr key={i}>
              <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{r.id.slice(0, 8)}...</td>
              <td>{r.subscription_id?.slice(0, 8)}...</td>
              <td>{r.resource_group || '-'}</td>
              <td><span className="tag">{r.timeframe}</span></td>
              <td>{r.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
