import React, { useState, useContext } from 'react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired } from '../components/QueryStates';
import { Flame, Info } from 'lucide-react';

const CATEGORIES = ['Compute', 'Storage', 'Network', 'AKS', 'Database', 'Identity'];
const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

const SEV_COLOR = {
  CRITICAL: 'heatmap-cell--critical',
  HIGH: 'heatmap-cell--high',
  MEDIUM: 'heatmap-cell--medium',
  LOW: 'heatmap-cell--low',
  INFO: 'heatmap-cell--info',
};

// Mock data: [category][severity] = { count, waste }
const MOCK = {
  Compute:  { CRITICAL: {count:8,  waste:9200}, HIGH: {count:14, waste:5400}, MEDIUM: {count:22, waste:2100}, LOW: {count:11, waste:580}, INFO: {count:3, waste:40} },
  Storage:  { CRITICAL: {count:2,  waste:1400}, HIGH: {count:6,  waste:1100}, MEDIUM: {count:15, waste:700}, LOW: {count:20, waste:210}, INFO: {count:8, waste:20} },
  Network:  { CRITICAL: {count:1,  waste:3200}, HIGH: {count:4,  waste:900},  MEDIUM: {count:9,  waste:310}, LOW: {count:7,  waste:90},  INFO: {count:2, waste:10} },
  AKS:      { CRITICAL: {count:5,  waste:7800}, HIGH: {count:9,  waste:3200}, MEDIUM: {count:7,  waste:840}, LOW: {count:3,  waste:140}, INFO: {count:1, waste:5} },
  Database: { CRITICAL: {count:0,  waste:0},    HIGH: {count:3,  waste:620},  MEDIUM: {count:8,  waste:290}, LOW: {count:12, waste:80},  INFO: {count:4, waste:15} },
  Identity: { CRITICAL: {count:0,  waste:0},    HIGH: {count:1,  waste:200},  MEDIUM: {count:4,  waste:60},  LOW: {count:9,  waste:30},  INFO: {count:6, waste:8} },
};

export default function WasteHeatmap() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const [tooltip, setTooltip] = useState(null); // {category, severity, data}
  const [view, setView] = useState('count'); // 'count' | 'waste'

  const maxCount = Math.max(...CATEGORIES.flatMap(c => SEVERITIES.map(s => MOCK[c][s].count)));
  const maxWaste = Math.max(...CATEGORIES.flatMap(c => SEVERITIES.map(s => MOCK[c][s].waste)));

  const intensity = (cat, sev) => {
    const d = MOCK[cat][sev];
    const val = view === 'count' ? d.count : d.waste;
    const max = view === 'count' ? maxCount : maxWaste;
    return max > 0 ? val / max : 0;
  };

  const totalWaste = CATEGORIES.flatMap(c => SEVERITIES.map(s => MOCK[c][s].waste)).reduce((a,b)=>a+b,0);
  const totalFindings = CATEGORIES.flatMap(c => SEVERITIES.map(s => MOCK[c][s].count)).reduce((a,b)=>a+b,0);
  const criticalCells = CATEGORIES.filter(c => MOCK[c].CRITICAL.count > 0).length;

  return (
    <div className="page-shell waste-heatmap-page">
      <PageHeader title="Waste Heatmap" subtitle="Visual breakdown of findings by category and severity" />
      {!subscription && <SubscriptionRequired message="Select a subscription." />}
      {subscription && (
        <>
          <div className="grid-3" style={{ marginBottom: '1.25rem' }}>
            <div className="stat-card danger"><div className="stat-label">Total Estimated Waste</div><div className="stat-value">{currency} {totalWaste.toLocaleString()}</div></div>
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
                        const d = MOCK[cat][sev];
                        const pct = intensity(cat, sev);
                        return (
                          <td key={sev}
                            className={`heatmap-cell ${SEV_COLOR[sev]}`}
                            style={{ '--intensity': pct }}
                            onMouseEnter={() => setTooltip({ cat, sev, d })}
                            onMouseLeave={() => setTooltip(null)}
                          >
                            <span className="heatmap-cell__val">
                              {view === 'count' ? d.count || '–' : d.waste > 0 ? `${currency} ${d.waste.toLocaleString()}` : '–'}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {tooltip && (
              <div className="heatmap-tooltip">
                <strong>{tooltip.cat} / {tooltip.sev}</strong>
                <span>{tooltip.d.count} finding{tooltip.d.count !== 1 ? 's' : ''}</span>
                <span>{currency} {tooltip.d.waste.toLocaleString()} estimated waste</span>
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
