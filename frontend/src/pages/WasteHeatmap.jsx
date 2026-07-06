import React, { useState, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired, LoadingState, ErrorState } from '../components/QueryStates';
import { Flame } from 'lucide-react';
import { fetchFindings } from '../api/azure';

const CATEGORIES = ['Compute', 'Storage', 'Network', 'AKS', 'Database', 'Identity'];
const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

const SEV_COLOR = {
  CRITICAL: 'heatmap-cell--critical',
  HIGH:     'heatmap-cell--high',
  MEDIUM:   'heatmap-cell--medium',
  LOW:      'heatmap-cell--low',
  INFO:     'heatmap-cell--info',
};

/** Map finding component/category fields → heatmap category buckets */
function bucketCategory(finding) {
  const raw = (finding.component || finding.resource_type || finding.category || '').toLowerCase();
  if (/vm|compute|virtual.machine|vmss/.test(raw))  return 'Compute';
  if (/storage|disk|snapshot/.test(raw))            return 'Storage';
  if (/network|ip|vnet|nic|lb|gateway|nsg/.test(raw)) return 'Network';
  if (/aks|kubernetes|k8s|container/.test(raw))     return 'AKS';
  if (/sql|postgres|cosmos|redis|database|db/.test(raw)) return 'Database';
  if (/keyvault|identity|auth|security/.test(raw))  return 'Identity';
  return null;
}

function bucketSeverity(finding) {
  const s = (finding.severity || '').toUpperCase();
  return SEVERITIES.includes(s) ? s : 'INFO';
}

function buildMatrix(findings) {
  const matrix = {};
  CATEGORIES.forEach(c => {
    matrix[c] = {};
    SEVERITIES.forEach(s => { matrix[c][s] = { count: 0, waste: 0 }; });
  });
  findings.forEach(f => {
    const cat = bucketCategory(f);
    const sev = bucketSeverity(f);
    if (!cat) return;
    matrix[cat][sev].count  += 1;
    matrix[cat][sev].waste  += Number(f.estimated_monthly_savings || f.savings || 0);
  });
  return matrix;
}

export default function WasteHeatmap() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const [tooltip, setTooltip] = useState(null);
  const [view, setView]       = useState('count');

  const { data: findings = [], isLoading, isError, error } = useQuery({
    queryKey: ['findings-heatmap', subscription],
    queryFn:  () => fetchFindings({ subscription_id: subscription, limit: 500 }),
    enabled:  !!subscription,
    staleTime: 5 * 60_000,
    select: data => Array.isArray(data) ? data : (data?.items ?? []),
  });

  const matrix   = buildMatrix(findings);
  const maxCount = Math.max(1, ...CATEGORIES.flatMap(c => SEVERITIES.map(s => matrix[c][s].count)));
  const maxWaste = Math.max(1, ...CATEGORIES.flatMap(c => SEVERITIES.map(s => matrix[c][s].waste)));

  const intensity = (cat, sev) => {
    const d   = matrix[cat][sev];
    const val = view === 'count' ? d.count : d.waste;
    const max = view === 'count' ? maxCount : maxWaste;
    return max > 0 ? val / max : 0;
  };

  const totalWaste    = CATEGORIES.flatMap(c => SEVERITIES.map(s => matrix[c][s].waste)).reduce((a,b)=>a+b,0);
  const totalFindings = CATEGORIES.flatMap(c => SEVERITIES.map(s => matrix[c][s].count)).reduce((a,b)=>a+b,0);
  const criticalCells = CATEGORIES.filter(c => matrix[c].CRITICAL.count > 0).length;

  return (
    <div className="page-shell waste-heatmap-page">
      <PageHeader title="Waste Heatmap" subtitle="Visual breakdown of findings by category and severity" />
      {!subscription && <SubscriptionRequired message="Select a subscription." />}
      {subscription && isLoading && <LoadingState message="Loading findings…" />}
      {subscription && isError   && <ErrorState message={error?.message || 'Failed to load findings.'} />}
      {subscription && !isLoading && !isError && (
        <>
          <div className="grid-3" style={{ marginBottom: '1.25rem' }}>
            <div className="stat-card danger"><div className="stat-label">Total Estimated Waste</div><div className="stat-value">{currency} {totalWaste.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div></div>
            <div className="stat-card accent"><div className="stat-label">Total Findings</div><div className="stat-value">{totalFindings}</div></div>
            <div className="stat-card warning"><div className="stat-label">Critical Categories</div><div className="stat-value">{criticalCells}</div></div>
          </div>

          <div className="card">
            <div className="card-section-head">
              <Flame size={15} className="text-danger" />
              <h3>Waste Heatmap</h3>
              <div className="segmented" style={{ marginLeft: 'auto' }}>
                <button className={`segmented__btn${view==='count'?' active':''}`} onClick={() => setView('count')}>By count</button>
                <button className={`segmented__btn${view==='waste'?' active':''}`} onClick={() => setView('waste')}>By waste</button>
              </div>
            </div>

            {totalFindings === 0 ? (
              <div className="empty-state" style={{ padding: '2rem' }}>
                <Flame size={28} />
                <p>No findings found for this subscription. Run an analysis to populate the heatmap.</p>
              </div>
            ) : (
              <div className="heatmap-wrap" style={{ overflowX: 'auto' }}>
                <table className="heatmap-table">
                  <thead>
                    <tr>
                      <th className="heatmap-th-label">Category \ Severity</th>
                      {SEVERITIES.map(s => <th key={s} className={`heatmap-th heatmap-th--${s.toLowerCase()}`}>{s}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {CATEGORIES.map(cat => (
                      <tr key={cat}>
                        <td className="heatmap-row-label">{cat}</td>
                        {SEVERITIES.map(sev => {
                          const d   = matrix[cat][sev];
                          const pct = intensity(cat, sev);
                          return (
                            <td key={sev}
                              className={`heatmap-cell ${SEV_COLOR[sev]}`}
                              style={{ '--intensity': pct }}
                              onMouseEnter={() => setTooltip({ cat, sev, d })}
                              onMouseLeave={() => setTooltip(null)}
                            >
                              <span className="heatmap-cell__val">
                                {view === 'count'
                                  ? (d.count || '–')
                                  : (d.waste > 0 ? `${currency} ${d.waste.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '–')}
                              </span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {tooltip && (
              <div className="heatmap-tooltip">
                <strong>{tooltip.cat} / {tooltip.sev}</strong>
                <span>{tooltip.d.count} finding{tooltip.d.count !== 1 ? 's' : ''}</span>
                <span>{currency} {tooltip.d.waste.toLocaleString(undefined, { maximumFractionDigits: 0 })} estimated waste</span>
              </div>
            )}

            <div className="heatmap-legend">
              <span className="heatmap-legend__label">Intensity:</span>
              <div className="heatmap-legend__scale" />
              <span className="heatmap-legend__lo">Low</span>
              <span className="heatmap-legend__hi">High</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
