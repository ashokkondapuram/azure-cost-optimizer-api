import React from 'react';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area, Legend,
} from 'recharts';
import { ArrowRight, AlertOctagon, AlertTriangle, Layers, Lightbulb } from 'lucide-react';
import { Link } from 'react-router-dom';
import AssetIcon from '../AssetIcon';
import { PAGE_ICONS } from '../../config/assetIcons';
import { formatCurrency, formatIsoDate } from '../../utils/format';
import { formatChartAxis } from '../../utils/costCurrency';
import { toDisplayText } from '../../utils/formatDisplay';
import TrendBadge from '../visual/TrendBadge';
import SeverityChip from '../visual/SeverityChip';
import DashboardDailyCostChart from './DashboardDailyCostChart';
import CollapsibleSection from './CollapsibleSection';
import {
  anomalyDays,
  CHART_RANK_COLORS,
  KPI_CARD_TYPE,
  mergeForecastSeries,
} from '../../utils/visualPolish';

const HEALTH_COLORS = {
  Healthy: '#22c55e',
  Warning: '#f59e0b',
  Critical: '#dc2626',
  Unknown: '#94a3b8',
};

const KPI_ICON = {
  weekly_cost: PAGE_ICONS.costs,
  monthly_trend: PAGE_ICONS.costs,
  open_findings: PAGE_ICONS.recommendations,
  estimated_savings: PAGE_ICONS.recommendations,
};

const KPI_SEMANTIC_ICON = {
  total_resources: Layers,
  resources_warning: AlertTriangle,
  resources_critical: AlertOctagon,
  advisor_findings: Lightbulb,
};

const HEALTH_KPI_IDS = ['resources_warning', 'advisor_findings', 'resources_critical'];

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

function parseDeltaPct(sub) {
  if (!sub) return null;
  const m = sub.match(/([↑↓])\s*([\d.]+)%/);
  if (!m) return null;
  return m[1] === '↓' ? -parseFloat(m[2]) : parseFloat(m[2]);
}

function KpiIcon({ kpiId, iconKey }) {
  const SemanticIcon = KPI_SEMANTIC_ICON[kpiId];
  if (SemanticIcon) {
    return (
      <span className="stat-card__icon stat-card__icon--semantic" aria-hidden>
        <SemanticIcon size={22} strokeWidth={2} />
      </span>
    );
  }
  return <AssetIcon iconKey={iconKey} size={22} className="stat-card__icon" alt="" />;
}

function buildForecastSeries(dailyChart, forecastDailyPoints = []) {
  return mergeForecastSeries(dailyChart, forecastDailyPoints);
}

function PortalPanel({ title, href, hrefLabel = 'View more', children, empty, emptyAction }) {
  return (
    <article className="portal-panel card">
      <header className="portal-panel__head">
        <h3 className="portal-panel__title">{title}</h3>
        {href && (
          <Link to={href} className="btn btn-ghost btn-sm">
            {hrefLabel}
            <ArrowRight size={14} />
          </Link>
        )}
      </header>
      {empty ? (
        <div className="portal-panel__empty">
          <p>{empty}</p>
          {emptyAction}
        </div>
      ) : children}
    </article>
  );
}

function KpiSkeletonRow({ count = 7 }) {
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
        const cardType = KPI_CARD_TYPE[kpi.id] || 'cost';
        const iconKey = KPI_ICON[kpi.id] || PAGE_ICONS.dashboard;
        const numericValue = Number(kpi.value ?? 0);
        const formattedValue = kpi.id === 'weekly_cost' || kpi.id === 'monthly_trend' || kpi.id === 'estimated_savings'
          ? formatCurrency(kpi.value, { currency: kpi.currency || currency, decimals: 0 })
          : numericValue.toLocaleString();
        const deltaPct = kpi.delta_pct ?? parseDeltaPct(kpi.sub);
        const deltaUsd = kpi.delta_usd;
        const isActive = numericValue > 0 && (kpi.tone === 'warn' || kpi.tone === 'warning' || kpi.tone === 'danger');

        const inner = (
          <>
            <KpiIcon kpiId={kpi.id} iconKey={iconKey} />
            <div className="stat-label">{kpi.label}</div>
            <div className="stat-card__value-row">
              <div className="stat-value">{formattedValue}</div>
              {deltaUsd != null && Number(deltaUsd) !== 0 && (
                <TrendBadge deltaAmount={deltaUsd} currency={kpi.currency || currency} invert />
              )}
              {deltaUsd == null && deltaPct != null && <TrendBadge deltaPct={deltaPct} invert />}
            </div>
            {kpi.sub && <div className="stat-sub">{kpi.sub}</div>}
          </>
        );

        const className = [
          'stat-card',
          `stat-card--${cardType}`,
          variant,
          'dashboard-kpi-stat-card',
          'dashboard-kpi-stat-card--enter',
          isActive ? 'dashboard-kpi-stat-card--active' : '',
        ].filter(Boolean).join(' ');
        const style = { '--kpi-enter-delay': `${index * 80}ms` };

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

function TopSpendWidget({ items, currency }) {
  if (!items?.length) return null;
  const maxCost = Math.max(...items.map((i) => i.cost_billing ?? i.cost_usd ?? 0));
  return (
    <ul className="top-spend-list">
      {items.slice(0, 8).map((item, i) => {
        const cost = item.cost_billing ?? item.cost_usd ?? 0;
        const pct = maxCost > 0 ? (cost / maxCost) * 100 : 0;
        const name = item.display_name || item.service || item.resource_type || 'Unknown';
        return (
          <li key={name} className="top-spend-row">
            <span className="top-spend-row__rank">#{i + 1}</span>
            <span className="top-spend-row__name">{toDisplayText(name)}</span>
            <div className="top-spend-row__bar-wrap">
              <div
                className="top-spend-row__bar"
                style={{ width: `${pct}%`, background: CHART_RANK_COLORS[i % CHART_RANK_COLORS.length] }}
              />
            </div>
            <span className="top-spend-row__value">
              {formatCurrency(cost, { currency: item.currency || currency, decimals: 0 })}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function utilChipClass(cpuText) {
  const n = parseFloat(String(cpuText || '').replace(/[^\d.]/g, ''));
  if (Number.isNaN(n)) return 'util-chip--muted';
  if (n < 20) return 'util-chip--low';
  if (n < 40) return 'util-chip--med';
  return 'util-chip--ok';
}

function UnderutilWidget({ items, currency }) {
  if (!items?.length) return null;
  return (
    <div className="table-wrap underutil-table-wrap">
      <table className="table underutil-table">
        <thead>
          <tr>
            <th>Resource</th>
            <th>CPU</th>
            <th>MTD cost</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.slice(0, 6).map((item) => {
            const cpu = item.avg_cpu || item.cpu || item.utilization || '—';
            return (
              <tr key={item.finding_id || item.resource_id}>
                <td className="underutil-table__name">
                  {toDisplayText(item.resource_name || item.resource_id)}
                </td>
                <td>
                  <span className={`util-chip ${utilChipClass(cpu)}`}>{toDisplayText(cpu)}</span>
                </td>
                <td>
                  {item.mtd_cost != null
                    ? formatCurrency(item.mtd_cost, { currency, decimals: 0 })
                    : item.estimated_savings_usd != null
                      ? formatCurrency(item.estimated_savings_usd, { currency, decimals: 0 })
                      : '—'}
                </td>
                <td>
                  <Link to="/optimization-hub?tab=actions" className="btn btn-ghost btn-sm">View</Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RecommendationsSection({ optimization, currency = 'CAD' }) {
  const items = optimization?.recommendations?.items || [];
  return (
    <section className="portal-actions card">
      <header className="portal-actions__head">
        <h3 className="dashboard-section__title">Top savings opportunities</h3>
        <Link to="/optimization-hub?tab=actions" className="btn btn-ghost btn-sm">
          View actions
          <ArrowRight size={14} />
        </Link>
      </header>
      {items.length === 0 ? (
        <div className="portal-panel__empty portal-panel__empty--inline">
          <p>No open findings yet. Run analysis to generate actions.</p>
          <div className="portal-actions__empty-ctas">
            <Link to="/history" className="btn btn-secondary btn-sm">View run history</Link>
            <Link to="/admin/optimization" className="btn btn-ghost btn-sm">Sync center</Link>
          </div>
        </div>
      ) : (
        <ul className="dashboard-action-list">
          {items.slice(0, 5).map((item) => (
            <li key={item.id} className="dashboard-action-list__item">
              <SeverityChip severity={item.severity} size={11} />
              <div className="dashboard-action-list__main">
                <span className="dashboard-action-list__name">
                  {toDisplayText(item.resource_name || item.rule_name)}
                </span>
                <span className="dashboard-action-list__rule">{toDisplayText(item.rule_name)}</span>
              </div>
              <span className="dashboard-action-list__savings savings-value">
                {formatCurrency(item.estimated_savings_usd ?? 0, { currency, decimals: 0 })}/mo
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PortalSkeleton() {
  return (
    <div className="dashboard-portal-skeleton" aria-busy="true">
      <KpiSkeletonRow />
      <div className="dashboard-row dashboard-row--primary">
        <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--panel skeleton" />
        <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--panel dashboard-kpi-skeleton--narrow skeleton" />
      </div>
    </div>
  );
}

function buildDashboardDailyChartData(daily, forecastDaily) {
  const dailyChart = daily.map((p) => ({
    date: p.date ? formatIsoDate(String(p.date).slice(0, 10)) : '',
    cost: p.cost_billing ?? p.cost_usd ?? 0,
  }));

  return {
    dailyChart,
    chartData: buildForecastSeries(dailyChart, forecastDaily),
  };
}

export default function DashboardPortal({
  portal,
  currency,
  optimization,
  analysisRuns,
  topSpendItems,
  underutilItems,
  budgets,
  dailyPoints,
  isLoading,
  costPeriodLabel,
  isExpanded,
  onToggleSection,
}) {
  if (!portal && isLoading) {
    return <PortalSkeleton />;
  }

  if (!portal) {
    return null;
  }

  const panels = portal.panels || {};
  const daily = panels.daily_cost_trend?.points || [];
  const forecastDaily = panels.daily_cost_trend?.forecast_points || [];
  const utilItems = panels.utilization_by_resource?.items || [];
  const costUtil = panels.cost_vs_utilization?.items || [];
  const healthSegs = (panels.resource_health_status?.segments || []).filter((s) => s.value > 0);
  const chartCurrency = panels.daily_cost_trend?.currency || currency;

  const kpisById = Object.fromEntries((portal.kpis || []).map((k) => [k.id, k]));

  const { dailyChart, chartData } = buildDashboardDailyChartData(daily, forecastDaily);
  const anomalies = anomalyDays(dailyPoints || daily, 1.5).map((a) => ({
    ...a,
    date: a.date ? formatIsoDate(a.date) : '',
  }));

  const budgetLine = (budgets || []).find((b) => b.amount > 0)?.amount ?? null;

  const runsData = [...(analysisRuns || [])].reverse().map((r) => ({
    date: r.analyzed_at ? formatIsoDate(String(r.analyzed_at).slice(0, 10)) : '',
    savings: r.total_savings_usd || 0,
  }));

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

      <CollapsibleSection
        id="cost_health"
        title="Cost & health"
        expanded={isExpanded ? isExpanded('cost_health') : true}
        onToggle={onToggleSection}
        actions={costPeriodLabel && (
          <span className="dashboard-section__period">{costPeriodLabel}</span>
        )}
      >
        <div className="dashboard-row dashboard-row--primary">
          <PortalPanel
            title={panels.daily_cost_trend?.title}
            href="/costs"
            hrefLabel="Cost explorer"
            empty={!dailyChart.length ? 'No cost data synced.' : null}
            emptyAction={!dailyChart.length && (
              <Link to="/costs" className="btn btn-secondary btn-sm">Open cost explorer</Link>
            )}
          >
            {dailyChart.length > 0 && (
              <DashboardDailyCostChart
                chartData={chartData}
                anomalies={anomalies}
                budgetLine={budgetLine}
                currency={currency}
                chartCurrency={chartCurrency}
                dailyPoints={dailyPoints || daily}
                monthlyComparison={panels.daily_cost_trend?.monthly_comparison || portal.hero_deltas}
              />
            )}
          </PortalPanel>

          <PortalPanel
            title={panels.resource_health_status?.title}
            empty={!healthSegs.length ? 'No inventory synced.' : null}
          >
            {healthSegs.length > 0 && (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={healthSegs}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={72}
                    label={false}
                  >
                    {healthSegs.map((s) => (
                      <Cell key={s.key} fill={HEALTH_COLORS[s.name] || '#6366f1'} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }} />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    formatter={(value) => value}
                    wrapperStyle={{ fontSize: '0.72rem' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </PortalPanel>
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        id="top_spend"
        title="Top spend & underutilization"
        expanded={isExpanded ? isExpanded('top_spend') : true}
        onToggle={onToggleSection}
      >
        <div className="dashboard-row dashboard-row--split">
          <PortalPanel
            title="Top spend by service"
            href="/costs"
            hrefLabel="Cost explorer"
            empty={!topSpendItems?.length ? 'No spend data synced.' : null}
          >
            <TopSpendWidget items={topSpendItems} currency={chartCurrency} />
          </PortalPanel>
          <PortalPanel
            title="Underutilized resources"
            href="/optimization-hub?tab=actions"
            hrefLabel="View actions"
            empty={!underutilItems?.length ? 'No underutilization findings.' : null}
          >
            <UnderutilWidget items={underutilItems} currency={chartCurrency} />
          </PortalPanel>
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        id="optimization"
        title="Optimization"
        expanded={isExpanded ? isExpanded('optimization') : true}
        onToggle={onToggleSection}
      >
        <div className="dashboard-row dashboard-row--split">
          <RecommendationsSection optimization={optimization} currency={currency} />

          <PortalPanel
            title={panels.cost_vs_utilization?.title}
            href="/optimization-hub?tab=actions"
            hrefLabel="View actions"
            empty={!costUtil.length ? 'No cost or utilization data.' : null}
          >
            {costUtil.length > 0 && (
              <ul className="portal-cost-util">
                {costUtil.map((row) => (
                  <li key={row.resource_id || row.name} className="portal-cost-util__row">
                    <span className="portal-cost-util__name">{toDisplayText(row.name)}</span>
                    <span className="portal-cost-util__cost">
                      {formatCurrency(row.cost, { currency: chartCurrency })}
                    </span>
                    <span className="portal-cost-util__util">{toDisplayText(row.utilization)}</span>
                  </li>
                ))}
              </ul>
            )}
          </PortalPanel>
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        id="insights"
        title="Insights"
        expanded={isExpanded ? isExpanded('insights') : true}
        onToggle={onToggleSection}
      >
        <div className="dashboard-row dashboard-row--split">
          <PortalPanel
            title={panels.utilization_by_resource?.title}
            empty={!utilItems.length ? 'No utilization data.' : null}
          >
            {utilItems.length > 0 && (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={utilItems} layout="vertical" margin={{ left: 8, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis type="number" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                  <YAxis type="category" dataKey="type" width={96} tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }}
                    formatter={(value, name, props) => {
                      const label = props?.payload?.utilization_label;
                      if (name === 'count' && label) {
                        return [`${value} resources · ${label}`, 'Count'];
                      }
                      return [value, name];
                    }}
                  />
                  <Bar dataKey="count" fill="#7c3aed" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </PortalPanel>

          <PortalPanel
            title="Analysis run savings"
            href="/history"
            hrefLabel="Run history"
            empty={!runsData.length ? 'No analysis runs yet.' : null}
            emptyAction={!runsData.length && (
              <Link to="/history" className="btn btn-secondary btn-sm">View run history</Link>
            )}
          >
            {runsData.length > 0 && (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={runsData}>
                  <defs>
                    <linearGradient id="savingsGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--success)" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="var(--success)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                  <YAxis
                    tick={{ fill: 'var(--text3)', fontSize: 10 }}
                    tickFormatter={(v) => formatChartAxis(v, currency)}
                  />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }}
                    formatter={(v) => [formatCurrency(v, { currency }), `Est. savings (${currency})`]}
                  />
                  <Area
                    type="monotone"
                    dataKey="savings"
                    stroke="var(--success)"
                    strokeWidth={2}
                    fill="url(#savingsGradient)"
                    dot={{ fill: 'var(--success)' }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </PortalPanel>
        </div>
      </CollapsibleSection>
    </>
  );
}
