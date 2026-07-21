import React from 'react';
import { ArrowRight, Layers, AlertOctagon, AlertTriangle, Lightbulb } from 'lucide-react';
import { Link } from 'react-router-dom';
import { PAGE_ICONS } from '../../config/assetIcons';
import { formatCurrency } from '../../utils/format';
import { toDisplayText } from '../../utils/formatDisplay';
import SeverityChip from '../visual/SeverityChip';
import AssetIcon from '../AssetIcon';
import { EmptyState } from '../QueryStates';

const KPI_ICON = {
  weekly_cost: PAGE_ICONS.costs,
  monthly_trend: PAGE_ICONS.costs,
  open_findings: PAGE_ICONS.recommendations,
  estimated_savings: PAGE_ICONS.recommendations,
};

const COST_KPI_IDS = new Set(['weekly_cost', 'monthly_trend', 'estimated_savings']);

const KPI_SEMANTIC_ICON = {
  total_resources: Layers,
  resources_degraded: AlertTriangle,
  resources_unavailable: AlertOctagon,
  advisor_findings: Lightbulb,
};

const HEALTH_KPI_IDS = ['resources_degraded', 'advisor_findings', 'resources_unavailable'];

const KPI_VARIANT = {
  default: 'accent',
  warn: 'warning',
  warning: 'warning',
  danger: 'danger',
  success: 'success',
};

function toneToVariant(tone) {
  return KPI_VARIANT[tone] || 'accent';
}

function KpiIcon({ kpiId, iconKey }) {
  const SemanticIcon = KPI_SEMANTIC_ICON[kpiId];
  if (SemanticIcon) {
    return (
      <span className="stat-card__icon stat-card__icon--semantic" aria-hidden>
        <SemanticIcon size={20} strokeWidth={2} />
      </span>
    );
  }
  return <AssetIcon iconKey={iconKey} size={20} className="stat-card__icon" alt="" />;
}

function KpiSkeletonRow({ count = 3 }) {
  return (
    <div className="dashboard-kpi-row dashboard-kpi-row--stat" aria-busy="true">
      {Array.from({ length: count }, (_, i) => i + 1).map((i) => (
        <div key={i} className="dashboard-kpi-skeleton dashboard-kpi-skeleton--card skeleton" />
      ))}
    </div>
  );
}

export function DashboardPortalKpis({ kpis, currency, isLoading, rowClassName = '' }) {
  if (isLoading) {
    return <KpiSkeletonRow count={HEALTH_KPI_IDS.length} />;
  }

  const rowClasses = ['dashboard-kpi-row', 'dashboard-kpi-row--stat', rowClassName]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={rowClasses}>
      {(kpis || []).map((kpi, index) => {
        const variant = toneToVariant(kpi.tone);
        const iconKey = KPI_ICON[kpi.id] || PAGE_ICONS.dashboard;
        const numericValue = Number(kpi.value ?? 0);
        const formattedValue = COST_KPI_IDS.has(kpi.id)
          ? formatCurrency(numericValue, { currency: kpi.currency || currency, decimals: 0 })
          : numericValue.toLocaleString();
        const isActive = numericValue > 0 && (kpi.tone === 'warn' || kpi.tone === 'warning' || kpi.tone === 'danger');

        const inner = (
          <>
            <KpiIcon kpiId={kpi.id} iconKey={iconKey} />
            <div className="stat-label">{kpi.label}</div>
            <div className="stat-card__value-row">
              <div className="stat-value">{formattedValue}</div>
            </div>
            {kpi.sub && <div className="stat-sub">{kpi.sub}</div>}
          </>
        );

        const className = [
          'stat-card',
          `stat-card--${kpi.id === 'advisor_findings' ? 'advisor' : 'cost'}`,
          variant,
          'dashboard-kpi-stat-card',
          'dashboard-kpi-stat-card--enter',
          isActive ? 'dashboard-kpi-stat-card--active' : '',
        ].filter(Boolean).join(' ');
        const style = { '--kpi-enter-delay': `${index * 60}ms` };

        if (kpi.href) {
          return (
            <Link
              key={kpi.id}
              to={kpi.href}
              className={`${className} dashboard-kpi-stat-link`}
              style={style}
            >
              {inner}
            </Link>
          );
        }
        return (
          <div key={kpi.id} className={className} style={style}>
            {inner}
          </div>
        );
      })}
    </div>
  );
}

function TopSavingsPreview({ optimization, currency }) {
  const items = (optimization?.recommendations?.items || []).slice(0, 3);
  if (!items.length) return null;

  return (
    <section className="portal-actions card dashboard-savings-preview">
      <header className="portal-actions__head dashboard-section__header--bar">
        <h3 className="dashboard-section__title dashboard-section__title--bar">Top savings</h3>
        <Link to="/action-centre?hasAction=1" className="btn btn-ghost btn-sm">
          View all
          <ArrowRight size={14} />
        </Link>
      </header>
      <ul className="dashboard-action-list dashboard-action-list--compact">
        {items.map((item) => (
          <li key={item.id} className="dashboard-action-list__item">
            <SeverityChip severity={item.severity} size={11} />
            <div className="dashboard-action-list__main">
              <span className="dashboard-action-list__name">
                {toDisplayText(item.resource_name || item.rule_name)}
              </span>
            </div>
            <span className="dashboard-action-list__savings savings-value">
              {formatCurrency(item.estimated_savings_usd ?? 0, { currency, decimals: 0 })}/mo
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PortalSkeleton() {
  return (
    <div className="dashboard-portal-skeleton" aria-busy="true">
      <KpiSkeletonRow />
    </div>
  );
}

export default function DashboardPortal({
  portal,
  currency,
  optimization,
  isLoading,
}) {
  if (!portal && isLoading) {
    return <PortalSkeleton />;
  }

  if (!portal) {
    return (
      <EmptyState
        iconKey={PAGE_ICONS.dashboard}
        message="Health and advisor metrics are not available yet. Sync resources or try again shortly."
      />
    );
  }

  const healthKpis = HEALTH_KPI_IDS
    .map((id) => (portal.kpis || []).find((k) => k.id === id))
    .filter(Boolean);

  return (
    <>
      <section className="dashboard-section dashboard-section--health dashboard-section--enter">
        <h3 className="dashboard-section__title dashboard-section__title--bar">Health & advisor</h3>
        <div className="dashboard-health-strip">
          <DashboardPortalKpis
            kpis={healthKpis}
            currency={currency}
            isLoading={false}
            rowClassName="dashboard-kpi-row--health"
          />
        </div>
      </section>

      <TopSavingsPreview optimization={optimization} currency={currency} />
    </>
  );
}
