import { toDisplayText } from './formatDisplay';

const GUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Page-specific scope lines shown after the subscription label. */
export const PAGE_SCOPE_DESCRIPTIONS = {
  dashboard: 'cost, health, and optimization at a glance',
  actionCentre: 'every resource, every recommendation, and every proposed change — prioritized by savings and severity so you act on what matters first',
  costExplorer: 'Azure spend trends, service breakdown, and period comparisons',
  resourceInventory: 'billed Azure resources — search, filter by service, and open resource details. Findings and optimization live in Action centre',
  settings: 'Azure, database, and platform configuration',
  budgets: 'Azure and custom budget thresholds for this subscription',
  governance: 'budgets and quota utilization',
  syncCenter: 'inventory sync, analysis jobs, and pipeline status',
  runHistory: 'browse past analysis runs and drill into historical findings',
  quota: 'regional quota usage and capacity risk',
  maintenance: 'planned Azure maintenance and service health events',
  wasteHeatmap: 'idle and orphaned resources by category and severity — open any resource for Azure Monitor metrics and full analysis',
  k8s: 'cluster utilization snapshots from the in-cluster agent',
  apiExplorer: 'OpenAPI routes and live API context for this subscription',
  optimizationActions: 'proposed workflow actions awaiting review or execution',
  engineConfig: 'rule profiles, thresholds, and engine behavior',
  cloudExplorer: 'billed Azure resources and resource-level cost context',
  savingsPlanner: 'model savings plans and reserved instances using live Azure cost data, Advisor, and your active commitments',
  costAnomalyDetector: 'rolling z-score analysis of daily Azure spend — flags unusual spikes and drops against the baseline window',
  reservationAdvisor: 'live Azure reservations and savings plans, merged with Advisor and engine commitment findings',
  demandForecaster: 'monthly spend history and end-of-month forecast from Azure Cost Management',
  adminOptimization: 'sync Azure inventory to the database, run the engine against stored resource data, and review recommendations',
  engineConfig: 'configure detection thresholds and enable or disable rules per profile',
};

export function isSubscriptionGuid(value) {
  return GUID_RE.test(String(value || '').trim());
}

export function shortenSubscriptionId(subscriptionId) {
  const id = String(subscriptionId || '').trim().toLowerCase();
  if (!id) return '';
  if (!isSubscriptionGuid(id)) return id;
  return `${id.slice(0, 8)}…`;
}

/**
 * Human-friendly subscription label for UI copy.
 * Never returns a bare full GUID when a readable name is unavailable.
 */
export function resolveSubscriptionLabel(subscriptionId, subscriptionOptions = []) {
  const id = String(subscriptionId || '').trim().toLowerCase();
  if (!id) return null;

  const match = subscriptionOptions.find(
    (entry) => String(entry.subscriptionId || '').trim().toLowerCase() === id,
  );
  const rawName = String(match?.displayName || '').trim();
  const normalizedName = rawName.toLowerCase();

  if (rawName && normalizedName !== id && !isSubscriptionGuid(rawName)) {
    return toDisplayText(rawName);
  }

  return 'This subscription';
}

export function formatSubscriptionOptionLabel(option) {
  if (!option) return '';
  const id = String(option.subscriptionId || '').trim();
  const label = resolveSubscriptionLabel(id, [option]);
  if (!label || label === 'This subscription') {
    return `Subscription ${shortenSubscriptionId(id)}`;
  }
  return `${label} (${shortenSubscriptionId(id)})`;
}

/**
 * "{Subscription label} — {scope description}" with optional suffix (e.g. period label).
 */
export function formatPageSubtitle(pageKey, subscriptionLabel, {
  suffix = '',
  fallback = '',
} = {}) {
  const scope = PAGE_SCOPE_DESCRIPTIONS[pageKey] || fallback;
  if (!scope) return suffix?.trim() || '';

  const base = subscriptionLabel
    ? `${subscriptionLabel} — ${scope}`
    : scope.charAt(0).toUpperCase() + scope.slice(1);

  const extra = String(suffix || '').trim();
  if (!extra) {
    return base.endsWith('.') ? base : `${base}.`;
  }
  if (extra.startsWith('.') || extra.startsWith('—')) return `${base}${extra}`;
  return `${base}. ${extra}`;
}

/** @deprecated Use resolveSubscriptionLabel */
export function dashboardSubscriptionTitle(subscriptionLabel) {
  return subscriptionLabel ? toDisplayText(subscriptionLabel) : null;
}
