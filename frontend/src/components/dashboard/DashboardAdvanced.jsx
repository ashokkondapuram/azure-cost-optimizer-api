import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, RefreshCw, DollarSign, Sparkles, Bell, Wallet,
} from 'lucide-react';
import { formatCurrency } from '../../utils/format';
import { toDisplayText } from '../../utils/formatDisplay';
import AdminOnly from '../AdminOnly';

const FRESHNESS_LABEL = {
  fresh: 'Up to date',
  recent: 'Synced recently',
  aging: 'Sync aging',
  stale: 'Sync stale',
  never: 'Not synced',
  unknown: 'Unknown',
};

function formatSyncTime(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return null;
  }
}

function syncTone(freshness) {
  if (freshness === 'fresh' || freshness === 'recent') return 'ok';
  if (freshness === 'aging') return 'warn';
  return 'muted';
}

export function DashboardHero({
  overview,
  currency,
  isLoading,
}) {
  if (isLoading || !overview) {
    return (
      <section className="dashboard-hero">
        <div className="dashboard-hero__content">
          <p className="dashboard-hero__sub">Loading dashboard…</p>
        </div>
      </section>
    );
  }

  const sync = overview.sync || {};
  const cost = overview.cost?.summary || {};
  const opt = overview.optimization?.summary || {};
  const inv = overview.inventory?.counts || {};
  const invSync = sync.inventory || {};
  const costSync = sync.cost || {};
  const analysisSync = sync.analysis || {};

  const mtdAmount = cost.pretax_total ?? cost.cost_usd_total ?? costSync.total_usd ?? 0;
  const mtdCurrency = cost.billing_currency || currency || 'USD';
  const critical = opt.by_severity?.CRITICAL ?? 0;
  const high = opt.by_severity?.HIGH ?? 0;

  return (
    <section className="dashboard-hero">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <p className="dashboard-hero__eyebrow">Subscription overview</p>
          <h2 className="dashboard-hero__title">
            {(inv.inventory_total ?? invSync.resource_count ?? 0).toLocaleString()} resources tracked
          </h2>
          <p className="dashboard-hero__sub">
            {(opt.open_findings ?? 0).toLocaleString()} open findings · PostgreSQL-backed data
          </p>
          <div className="dashboard-hero__actions">
            <Link to="/action-centre" className="btn btn-primary btn-sm">
              Open action centre
              <ArrowRight size={14} />
            </Link>
            <Link to="/costs" className="btn btn-ghost btn-sm">Cost explorer</Link>
            <AdminOnly>
              <Link to="/admin/optimization" className="btn btn-ghost btn-sm">
                Sync center
              </Link>
            </AdminOnly>
          </div>
        </div>

        <div className="dashboard-hero__metrics">
          <div className="dashboard-hero__metric">
            <span className="dashboard-hero__metric-value">
              {formatCurrency(mtdAmount, { currency: mtdCurrency, decimals: 0 })}
            </span>
            <span className="dashboard-hero__metric-label">MTD spend</span>
          </div>
          <div className="dashboard-hero__metric dashboard-hero__metric--success">
            <span className="dashboard-hero__metric-value">
              {formatCurrency(opt.total_estimated_savings_usd ?? 0, { currency, decimals: 0 })}
            </span>
            <span className="dashboard-hero__metric-label">Est. savings</span>
          </div>
          <div className="dashboard-hero__metric dashboard-hero__metric--danger">
            <span className="dashboard-hero__metric-value">{critical}</span>
            <span className="dashboard-hero__metric-label">Critical</span>
          </div>
          <div className="dashboard-hero__metric dashboard-hero__metric--warning">
            <span className="dashboard-hero__metric-value">{high}</span>
            <span className="dashboard-hero__metric-label">High</span>
          </div>
        </div>
      </div>

      <div className="dashboard-hero__sync">
        <div className="dashboard-hero__sync-head">
          <RefreshCw size={15} aria-hidden />
          <span>Data freshness</span>
        </div>
        <div className="dashboard-hero__sync-pills">
          {[
            { label: 'Inventory', freshness: invSync.freshness, at: invSync.last_synced_at },
            { label: 'Cost', freshness: costSync.freshness, at: costSync.last_synced_at },
            {
              label: 'Analysis',
              freshness: analysisSync.last_status === 'completed' ? 'fresh' : analysisSync.last_status || 'never',
              at: analysisSync.last_job_at,
            },
          ].map((pill) => (
            <div
              key={pill.label}
              className={`dashboard-hero__sync-pill dashboard-hero__sync-pill--${syncTone(pill.freshness)}`}
              title={formatSyncTime(pill.at) || undefined}
            >
              <span className="dashboard-hero__sync-pill-label">{pill.label}</span>
              <span className="dashboard-hero__sync-pill-value">
                {FRESHNESS_LABEL[pill.freshness] || pill.freshness}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function DashboardCostSection({ cost, currency, isLoading }) {
  const daily = cost?.daily?.points || [];
  const topSpend = cost?.top_spend?.items || [];
  const billingCurrency = cost?.daily?.billing_currency || cost?.top_spend?.billing_currency || currency;

  if (isLoading) {
    return (
      <section className="dashboard-row">
        <div className="card dashboard-panel"><p>Loading cost data…</p></div>
      </section>
    );
  }

  return (
    <section className="dashboard-row dashboard-row--cost">
      <div className="card dashboard-panel dashboard-panel--chart">
        <header className="dashboard-panel__head">
          <DollarSign size={18} aria-hidden />
          <div>
            <h3 className="dashboard-section__title">Daily spend</h3>
            <p className="dashboard-section__sub">Month to date from synced cost export</p>
          </div>
        </header>
        {daily.length === 0 ? (
          <div className="empty-state dashboard-panel__empty">
            <p>No daily cost data synced yet</p>
            <Link to="/costs" className="btn btn-ghost btn-sm">Sync costs</Link>
          </div>
        ) : (
          <DashboardDailySparkline points={daily} currency={billingCurrency} />
        )}
      </div>

      <div className="card dashboard-panel">
        <header className="dashboard-panel__head">
          <div>
            <h3 className="dashboard-section__title">Top spend</h3>
            <p className="dashboard-section__sub">Highest-cost resources this month</p>
          </div>
        </header>
        {topSpend.length === 0 ? (
          <div className="empty-state dashboard-panel__empty">
            <p>No resource costs yet</p>
          </div>
        ) : (
          <ul className="dashboard-topspend dashboard-topspend--compact">
            {topSpend.map((item) => {
              const amount = item.cost_billing ?? item.cost_usd ?? 0;
              const label = item.resource_name || item.resource_id?.split('/').pop() || 'Resource';
              return (
                <li key={item.resource_id} className="dashboard-topspend__row dashboard-topspend__row--compact">
                  <div className="dashboard-topspend__meta">
                    <span className="dashboard-topspend__name">{toDisplayText(label)}</span>
                    <span className="dashboard-topspend__service">{toDisplayText(item.service_name)}</span>
                  </div>
                  <span className="dashboard-topspend__amount">
                    {billingCurrency} {amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

function DashboardDailySparkline({ points, currency }) {
  const max = Math.max(...points.map((p) => p.cost_billing ?? p.cost_usd ?? 0), 1);
  return (
    <div className="dashboard-sparkline" role="img" aria-label="Daily spend trend">
      {points.map((p) => {
        const amount = p.cost_billing ?? p.cost_usd ?? 0;
        const h = Math.max(8, (amount / max) * 100);
        const label = p.date
          ? new Date(p.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
          : '';
        return (
          <div key={p.date} className="dashboard-sparkline__bar" title={`${label}: ${currency} ${amount.toFixed(2)}`}>
            <div className="dashboard-sparkline__fill" style={{ height: `${h}%` }} />
            <span className="dashboard-sparkline__label">{label.split(' ')[1]}</span>
          </div>
        );
      })}
    </div>
  );
}

export function DashboardActionsSection({ optimization, monitoring, budgets }) {
  const recs = optimization?.recommendations?.items || [];
  const underutil = optimization?.underutil?.items || [];
  const alerts = monitoring?.items || [];
  const budgetRows = budgets || [];

  return (
    <>
      <section className="dashboard-actions">
        <div className="card dashboard-panel">
          <header className="dashboard-panel__head">
            <Sparkles size={18} aria-hidden />
            <div>
              <h3 className="dashboard-section__title">Top findings</h3>
              <p className="dashboard-section__sub">Highest savings from the optimization engine</p>
            </div>
            <Link to="/action-centre" className="btn btn-ghost btn-sm">View all</Link>
          </header>
          {recs.length === 0 ? (
            <p className="dashboard-panel__empty-text">No open findings yet</p>
          ) : (
            <ul className="dashboard-action-list">
              {recs.map((item) => (
                <li key={item.id} className="dashboard-action-list__item">
                  <div className="dashboard-action-list__main">
                    <span className={`severity-pill severity-pill--${(item.severity || '').toLowerCase()}`}>
                      {item.severity}
                    </span>
                    <span className="dashboard-action-list__name">
                      {toDisplayText(item.resource_name || item.rule_name)}
                    </span>
                    <span className="dashboard-action-list__rule">{toDisplayText(item.rule_name)}</span>
                  </div>
                  <span className="dashboard-action-list__savings">
                    ${(item.estimated_savings_usd ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card dashboard-panel">
          <header className="dashboard-panel__head">
            <div>
              <h3 className="dashboard-section__title">Underutilized resources</h3>
              <p className="dashboard-section__sub">Idle or oversized workloads</p>
            </div>
          </header>
          {underutil.length === 0 ? (
            <p className="dashboard-panel__empty-text">No underutilization findings</p>
          ) : (
            <ul className="dashboard-action-list">
              {underutil.map((item) => (
                <li key={item.finding_id} className="dashboard-action-list__item">
                  <div className="dashboard-action-list__main">
                    <span className="dashboard-action-list__name">
                      {toDisplayText(item.resource_name || item.resource_id?.split('/').pop())}
                    </span>
                    <span className="dashboard-action-list__rule">{toDisplayText(item.rule_id)}</span>
                  </div>
                  <span className="dashboard-action-list__savings">
                    ${(item.estimated_savings_usd ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {(budgetRows.length > 0 || alerts.length > 0) && (
        <section className="dashboard-row dashboard-row--meta">
          {budgetRows.length > 0 && (
            <div className="card dashboard-panel dashboard-panel--compact">
              <header className="dashboard-panel__head">
                <Wallet size={16} aria-hidden />
                <h3 className="dashboard-section__title">Budgets</h3>
              </header>
              <ul className="dashboard-meta-list">
                {budgetRows.slice(0, 4).map((b) => {
                  const pct = b.amount > 0 ? Math.min(100, ((b.currentSpend ?? 0) / b.amount) * 100) : 0;
                  return (
                    <li key={b.id || b.name} className="dashboard-meta-list__item">
                      <span className="dashboard-meta-list__label">{toDisplayText(b.name)}</span>
                      <div className="dashboard-meta-list__bar-wrap">
                        <div className="dashboard-meta-list__bar" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="dashboard-meta-list__value">{Math.round(pct)}%</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          {alerts.length > 0 && (
            <div className="card dashboard-panel dashboard-panel--compact">
              <header className="dashboard-panel__head">
                <Bell size={16} aria-hidden />
                <h3 className="dashboard-section__title">Metric alerts</h3>
                <span className="dashboard-meta-list__badge">{monitoring?.count ?? alerts.length}</span>
              </header>
              <ul className="dashboard-meta-list dashboard-meta-list--names">
                {alerts.slice(0, 5).map((a) => (
                  <li key={a.resource_id} className="dashboard-meta-list__item">
                    <span className="dashboard-meta-list__label">{toDisplayText(a.name)}</span>
                    <span className="dashboard-meta-list__value">{toDisplayText(a.severity) || '—'}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </>
  );
}
