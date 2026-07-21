import React, { useContext, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, Search } from 'lucide-react';
import { AppCtx } from '../../../App';
import { fetchFindingsSummary } from '../../../api/azure';
import { fetchPipelineServices } from '../../../api/pipeline';
import useFindingsIndex from '../../../hooks/useFindingsIndex';
import { LoadingState } from '../../QueryStates';
import { formatCurrency } from '../../../utils/format';
import { useCloudExplorer } from '../../../context/CloudExplorerContext';
import { openFindingsCount } from '../../../utils/findingsSummaryUtils';
import WizSourceBreakdown from '../WizSourceBreakdown';

const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

function SeverityBars({ bySeverity, total }) {
  const max = Math.max(total, 1);
  return (
    <div className="wiz-severity-bars">
      {SEVERITY_ORDER.map((sev) => {
        const count = bySeverity?.[sev] ?? 0;
        if (total > 0 && count === 0) return null;
        return (
          <div key={sev} className="wiz-sev-bar">
            <span>{sev}</span>
            <div className="wiz-sev-bar__track">
              <div
                className={`wiz-sev-bar__fill wiz-sev-bar__fill--${sev}`}
                style={{ width: `${(count / max) * 100}%` }}
              />
            </div>
            <span>{count}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function WizOverviewPanel() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const { setTab } = useCloudExplorer();
  const [q, setQ] = useState('');

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['findings-summary', subscription, 'inventory'],
    queryFn: () => fetchFindingsSummary({
      subscription_id: subscription,
      inventory_only: true,
    }),
    enabled: !!subscription,
  });

  const { data: services } = useQuery({
    queryKey: ['pipeline-services'],
    queryFn: fetchPipelineServices,
    staleTime: 10 * 60_000,
  });

  const { findings, isLoading: findingsLoading } = useFindingsIndex(
    subscription,
    { inventoryOnly: true },
  );

  const topIssues = useMemo(() => {
    const sorted = [...findings].sort((a, b) => {
      const sev = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 };
      const sd = (sev[a.severity] ?? 9) - (sev[b.severity] ?? 9);
      if (sd !== 0) return sd;
      return (b.estimated_savings_usd || 0) - (a.estimated_savings_usd || 0);
    });
    const filtered = q
      ? sorted.filter((f) => {
        const hay = `${f.rule_name} ${f.resource_name} ${f.resource_id}`.toLowerCase();
        return hay.includes(q.toLowerCase());
      })
      : sorted;
    return filtered.slice(0, 12);
  }, [findings, q]);

  const engineCount = services?.services?.filter((s) => s.has_engine).length ?? 0;

  if (!subscription) {
    return (
      <div className="wiz-empty">
        <strong>Select a subscription</strong>
        Choose a subscription to explore issues, inventory, and services.
      </div>
    );
  }

  if (summaryLoading || findingsLoading) {
    return <LoadingState message="Loading cloud overview…" />;
  }

  const bySeverity = summary?.by_severity || summary?.severity || {};
  const openTotal = openFindingsCount(summary) || findings.length;

  return (
    <div className="wiz-panel" id="wiz-panel-overview" role="tabpanel" aria-labelledby="wiz-tab-overview">
      <div className="wiz-overview-grid">
        <section className="wiz-card">
          <header className="wiz-card__head">
            <h3>Top issues</h3>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setTab('issues')}>
              View all
              <ArrowRight size={14} />
            </button>
          </header>
          <div className="wiz-toolbar">
            <span className="wiz-search" style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <Search size={14} style={{ position: 'absolute', left: 10, opacity: 0.5 }} />
              <input
                type="search"
                placeholder="Filter issues…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                style={{ paddingLeft: 30, width: '100%' }}
                aria-label="Filter top issues"
              />
            </span>
          </div>
          <div className="wiz-table-wrap">
            <table className="wiz-table">
              <thead>
                <tr>
                  <th>Issue</th>
                  <th>Resource</th>
                  <th>Savings</th>
                </tr>
              </thead>
              <tbody>
                {topIssues.map((f) => (
                  <tr key={f.id} onClick={() => setTab('issues')}>
                    <td>
                      <span className={`wiz-sev-dot wiz-sev-dot--${f.severity}`} />
                      {f.rule_name}
                    </td>
                    <td>{f.resource_name || (f.resource_id || '').split('/').pop()}</td>
                    <td style={{ color: 'var(--success)', fontWeight: 600 }}>
                      {f.estimated_savings_usd > 0
                        ? formatCurrency(f.estimated_savings_usd, { currency, decimals: 0 })
                        : '—'}
                    </td>
                  </tr>
                ))}
                {topIssues.length === 0 && (
                  <tr>
                    <td colSpan={3} className="wiz-empty">No open issues</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <section className="wiz-card">
            <header className="wiz-card__head">
              <h3>Issue severity</h3>
              <span className="wiz-pill">{openTotal.toLocaleString()} open</span>
            </header>
            {summary && <WizSourceBreakdown summary={summary} />}
            <SeverityBars bySeverity={bySeverity} total={openTotal} />
          </section>

          <section className="wiz-card">
            <header className="wiz-card__head">
              <h3>Service coverage</h3>
            </header>
            <div style={{ padding: '1rem' }}>
              <p style={{ margin: '0 0 0.75rem', color: 'var(--text2)', fontSize: '0.85rem' }}>
                {engineCount} of {services?.count ?? 0} services have optimization engines wired.
              </p>
              <div className="wiz-pill-row">
                <span className="wiz-pill wiz-pill--ok">Engines {engineCount}</span>
                <span className="wiz-pill">Catalog {services?.count ?? 0}</span>
              </div>
              <div style={{ marginTop: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                <Link to="/action-centre?hasAction=1" className="btn btn--ghost btn--sm" style={{ justifyContent: 'flex-start' }}>
                  Proposed actions
                  <ArrowRight size={14} />
                </Link>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setTab('services')}>
                  Browse services
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
