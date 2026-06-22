import React, { useEffect, useState } from 'react';
import { fetchK8sUtilization } from '../api/client';

export default function K8sPage() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchK8sUtilization()
      .then(r => setRecords(r.data || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="loading">Loading K8s data...</p>;
  if (error) return <p className="error">{error}</p>;

  const nodes = records.filter(r => !r.pod);
  const pods = records.filter(r => r.pod);

  return (
    <div>
      <div className="stat-row">
        <div className="stat"><div className="label">Nodes tracked</div><div className="value">{nodes.length}</div></div>
        <div className="stat"><div className="label">Pod records</div><div className="value">{pods.length}</div></div>
      </div>
      <div className="card">
        <h2>Node Utilization</h2>
        <table>
          <thead><tr><th>Cluster</th><th>Node</th><th>CPU</th><th>Memory</th><th>Recorded At</th></tr></thead>
          <tbody>
            {nodes.slice(0, 50).map((r, i) => (
              <tr key={i}>
                <td>{r.cluster || '-'}</td>
                <td>{r.node}</td>
                <td>{r.cpu || '-'}</td>
                <td>{r.memory || '-'}</td>
                <td>{r.recorded_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h2>Pod Utilization</h2>
        <table>
          <thead><tr><th>Namespace</th><th>Pod</th><th>CPU</th><th>Memory</th><th>Recorded At</th></tr></thead>
          <tbody>
            {pods.slice(0, 100).map((r, i) => (
              <tr key={i}>
                <td>{r.namespace || '-'}</td>
                <td>{r.pod}</td>
                <td>{r.cpu || '-'}</td>
                <td>{r.memory || '-'}</td>
                <td>{r.recorded_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
