import {
  countCostDrivers,
  countCostSignalTriggers,
  filterMetricsBundleForCostSignals,
} from './costSignalsFilters';
import { shouldCollapseMetricsSection } from '../it-services/registry';
import { resourceLabelForRow } from '../config/assetIcons';
import { resolveRelatedResources } from './drawerRelatedResources';
import {
  hasDrawerPropertyMetrics,
  shouldHideGenericMetrics,
} from './drawerResourceTypeMetrics';
import {
  resolveDrawerCanonicalType,
  resourceUsesCpuMemoryTrends,
  trendMetricKeysForResource,
  trendMetricKeysForType,
  hasTrendSummaryMetrics,
  noTrendSummaryMetricsMessage,
  TREND_SUMMARY_METRICS_BY_TYPE,
} from './drawerTrendMetrics';

export {
  resolveDrawerCanonicalType,
  resourceUsesCpuMemoryTrends,
  trendMetricKeysForResource,
  trendMetricKeysForType,
  hasTrendSummaryMetrics,
  noTrendSummaryMetricsMessage,
  TREND_SUMMARY_METRICS_BY_TYPE,
} from './drawerTrendMetrics';

/** Insight drawer nav section ids. */
export const DRAWER_SECTION_IDS = {
  overview: 'overview',
  findings: 'findings',
  properties: 'properties',
  costDrivers: 'cost-drivers',
  trends: 'trends',
  metrics: 'metrics',
  cost: 'cost',
  analysis: 'analysis',
  advisor: 'advisor',
  actions: 'actions',
  tags: 'tags',
  pools: 'pools',
};

/** Full sentence-case labels for drawer section nav (no abbreviations). */
export const DRAWER_SECTION_LABELS = {
  [DRAWER_SECTION_IDS.overview]: 'Overview',
  [DRAWER_SECTION_IDS.findings]: 'Findings',
  [DRAWER_SECTION_IDS.properties]: 'Properties',
  [DRAWER_SECTION_IDS.metrics]: 'Metrics',
  [DRAWER_SECTION_IDS.costDrivers]: 'Cost drivers',
  [DRAWER_SECTION_IDS.trends]: 'Trends',
  [DRAWER_SECTION_IDS.cost]: 'Cost',
  [DRAWER_SECTION_IDS.analysis]: 'Insights',
  [DRAWER_SECTION_IDS.advisor]: 'Advisor',
  [DRAWER_SECTION_IDS.actions]: 'Actions',
  [DRAWER_SECTION_IDS.tags]: 'Tags',
  [DRAWER_SECTION_IDS.pools]: 'Node pools',
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const BILLING_ARM_FRAGMENTS = [
  '/microsoft.billingbenefits/',
  '/microsoft.capacity/reservationorders/',
  '/providers/microsoft.billingbenefits/',
];

const BILLING_INAPPROPRIATE_RULE_IDS = new Set([
  'COST_HIGH_SPEND_REVIEW',
]);

/** ARM provider/type from resource row. */
export function resolveArmType(resource) {
  if (!resource) return '';
  const props = resource.properties || {};
  const fromProps = props.armResourceType || props.arm_resource_type || resource.armResourceType;
  if (fromProps && String(fromProps).includes('/')) {
    return String(fromProps).toLowerCase();
  }
  const rid = String(resource.id || resource.resource_id || '').toLowerCase();
  const type = String(resource.type || '').toLowerCase();
  if (type.includes('/')) return type;
  if (rid.includes('/providers/')) {
    const parts = rid.split('/');
    const idx = parts.indexOf('providers');
    if (idx >= 0 && parts[idx + 2]) {
      return `${parts[idx + 1]}/${parts[idx + 2]}`.toLowerCase();
    }
  }
  return type;
}

export function isUuidLike(value) {
  const text = String(value || '').trim();
  return UUID_RE.test(text);
}

export function isBillingOrCommitmentResource(resource) {
  const armType = resolveArmType(resource);
  const rid = String(resource?.id || resource?.resource_id || '').toLowerCase();
  if (BILLING_ARM_FRAGMENTS.some((frag) => rid.includes(frag) || armType.includes(frag.replace('/providers', '')))) {
    return true;
  }
  if (armType.startsWith('microsoft.billingbenefits/')) return true;
  const service = String(resource?.azureServiceName || resource?.service_name || '').toLowerCase();
  return service.includes('billing benefits') || service.includes('reservation');
}

export function resolveResourceDisplayName(resource) {
  if (!resource) return 'Resource';
  const rawName = resource.name || resource.resource_name || '';
  const rid = resource.id || resource.resource_id || '';
  const typeLabel = resourceLabelForRow(resource)
    || humanizeArmType(resolveArmType(resource));

  if (rawName && !isUuidLike(rawName)) return rawName;

  if (typeLabel) {
    const leaf = rid.split('/').pop() || '';
    const shortId = leaf && isUuidLike(leaf) ? leaf.slice(0, 8) : leaf;
    return shortId ? `${typeLabel} · ${shortId}` : typeLabel;
  }

  return rid.split('/').pop() || 'Resource';
}

function humanizeArmType(armType) {
  if (!armType) return '';
  const leaf = armType.split('/').pop() || armType;
  return leaf
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/orders?$/i, ' order')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function filterDrawerFindings(findings, resource) {
  if (!isBillingOrCommitmentResource(resource)) return findings;
  return (findings || []).filter((f) => !BILLING_INAPPROPRIATE_RULE_IDS.has(f.rule_id));
}

/** Collapse dense drawer sections when item count exceeds this threshold. */
export const DRAWER_COLLAPSE_ITEM_THRESHOLD = 8;

export function resolveCanonicalType(resource, apiPath = '') {
  return resolveDrawerCanonicalType(resource, apiPath);
}

export function shouldCollapseDrawerItems(count) {
  return Number(count) > DRAWER_COLLAPSE_ITEM_THRESHOLD;
}

export function hasCostDriversContent(metricsData) {
  if (!metricsData) return false;
  const filtered = filterMetricsBundleForCostSignals(metricsData);
  return countCostDrivers(filtered) > 0 || countCostSignalTriggers(filtered) > 0;
}

export function hasTrendsContent({
  capabilities,
  bundleAnalysis,
  bundleMetrics,
  resource,
  findings = [],
  apiPath = '',
  canonicalType = '',
} = {}) {
  if (!capabilities?.showMetrics && !capabilities?.showAnalysis) return false;
  const trends = bundleAnalysis?.trends;
  if (trends?.cost_vs_prev_month_pct != null) return true;
  const resolvedCanonical = canonicalType || resolveCanonicalType(resource, apiPath);
  if (resourceUsesCpuMemoryTrends(resource, apiPath)) {
    if (trends?.cpu_trend || trends?.memory_trend) return true;
  }
  if (hasDrawerPropertyMetrics(
    resource,
    bundleMetrics,
    resolvedCanonical,
    resolveArmType(resource),
  )) {
    return true;
  }
  if (trendMetricKeysForResource(resource, apiPath).length > 0) return true;
  const hasMetrics = (bundleMetrics?.metrics?.length || 0) + (bundleMetrics?.derived?.length || 0) > 0;
  if (hasMetrics && hasTrendSummaryMetrics(resolvedCanonical, resolveArmType(resource))) return true;
  const related = resolveRelatedResources(resource, {
    findings,
    dependencies: bundleAnalysis?.dependencies,
    inventoryProperties: bundleMetrics?.inventory_properties,
  });
  return related.length > 0;
}

export function buildDrawerSections({
  resolved,
  capabilities,
  displayFindings = [],
  displayTags = {},
  drawerResource,
  bundleMetrics,
  bundleAnalysis,
  bundlePending = false,
  hasAnalysisInsights = false,
  hasCostSection = false,
  hasPropertiesSection = false,
  advisorRecommendations = [],
  proposedActions = [],
  totalCost = 0,
  apiPath = '',
} = {}) {
  if (!resolved) return [{ id: DRAWER_SECTION_IDS.overview, label: DRAWER_SECTION_LABELS.overview }];

  const sections = [{ id: DRAWER_SECTION_IDS.overview, label: DRAWER_SECTION_LABELS.overview }];

  if (hasPropertiesSection) {
    sections.push({
      id: DRAWER_SECTION_IDS.properties,
      label: DRAWER_SECTION_LABELS.properties,
    });
  }

  if (displayFindings.length > 0 || capabilities.billing) {
    sections.push({
      id: DRAWER_SECTION_IDS.findings,
      label: capabilities.billing ? 'Spend' : DRAWER_SECTION_LABELS.findings,
      badge: displayFindings.length,
    });
  }

  const costDriversVisible = hasCostDriversContent(bundleMetrics)
    || (bundlePending && capabilities.showMetrics);
  const costDriverBadge = bundleMetrics
    ? (() => {
      const filtered = filterMetricsBundleForCostSignals(bundleMetrics);
      const driverCount = countCostDrivers(filtered);
      const triggerCount = countCostSignalTriggers(filtered);
      return driverCount || triggerCount || undefined;
    })()
    : undefined;

  const trendsVisible = hasTrendsContent({
    capabilities,
    bundleAnalysis,
    bundleMetrics,
    resource: drawerResource,
    findings: displayFindings,
    apiPath,
  }) || (bundlePending && capabilities.showAnalysis);

  if (capabilities.showMetrics) {
    sections.push({ id: DRAWER_SECTION_IDS.metrics, label: DRAWER_SECTION_LABELS.metrics });
  }

  if (costDriversVisible && !capabilities.billing) {
    sections.push({
      id: DRAWER_SECTION_IDS.costDrivers,
      label: DRAWER_SECTION_LABELS[DRAWER_SECTION_IDS.costDrivers],
      badge: costDriverBadge,
    });
  }

  if (trendsVisible && !capabilities.billing) {
    sections.push({ id: DRAWER_SECTION_IDS.trends, label: DRAWER_SECTION_LABELS.trends });
  }

  if (hasCostSection) {
    sections.push({ id: DRAWER_SECTION_IDS.cost, label: DRAWER_SECTION_LABELS.cost });
  }

  if (capabilities.showAnalysis && (hasAnalysisInsights || bundlePending)) {
    sections.push({ id: DRAWER_SECTION_IDS.analysis, label: DRAWER_SECTION_LABELS.analysis });
  }

  if (capabilities.showAdvisor) {
    sections.push({
      id: DRAWER_SECTION_IDS.advisor,
      label: DRAWER_SECTION_LABELS.advisor,
      badge: advisorRecommendations.length,
    });
  }

  if (proposedActions.length > 0) {
    sections.push({
      id: DRAWER_SECTION_IDS.actions,
      label: DRAWER_SECTION_LABELS.actions,
      badge: proposedActions.length,
    });
  }

  if (capabilities.showTags) {
    sections.push({
      id: DRAWER_SECTION_IDS.tags,
      label: DRAWER_SECTION_LABELS.tags,
      badge: Object.keys(displayTags).length,
    });
  }

  if (capabilities.showPools) {
    sections.push({
      id: DRAWER_SECTION_IDS.pools,
      label: DRAWER_SECTION_LABELS.pools,
      badge: drawerResource?._pools?.length || 0,
    });
  }

  return sections;
}

export function getDrawerCapabilities(resource, {
  apiPath = '',
  rid = '',
  subscription = '',
  hasNodePools = false,
  advisorCount = 0,
} = {}) {
  const billing = isBillingOrCommitmentResource(resource);
  const costExportOnly = Boolean(resource?.costExportOnly);
  const optimizable = !billing && !costExportOnly;
  const canonicalType = resolveCanonicalType(resource, apiPath);
  const armType = resolveArmType(resource);
  const hideGenericMetrics = shouldHideGenericMetrics(canonicalType, armType);

  return {
    billing,
    costExportOnly,
    showMetrics: Boolean(
      rid
      && optimizable
      && !hideGenericMetrics
      && !shouldCollapseMetricsSection(resource, apiPath),
    ),
    showAdvisor: Boolean(rid && optimizable && advisorCount > 0),
    showAnalysis: Boolean(rid && optimizable),
    showTags: Boolean(rid && subscription && optimizable),
    showPools: hasNodePools,
    poolsNote: hasNodePools && resource?._nodeAutoProvisioningEnabled
      ? 'Node auto provisioning manages node pool scale. Manual scale-down recommendations are suppressed.'
      : null,
    overviewNote: billing
      ? 'Billing commitment record — not a workload resource. Review coverage and utilization in Savings planner, not rightsizing here.'
      : costExportOnly
        ? 'Cost export line — sync inventory to unlock full properties and metrics.'
        : null,
  };
}
