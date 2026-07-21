/** Action centre v2 — map API findings/resources to concept-v2 table rows. */

import { normalizeArmId } from './findingDedupe';
import { isActionCentreFinding, topFindingHeadline } from './findingFilters';
import {
  aggregatedRecommendationHeadline,
  expandFindingRecommendations,
  recommendationCountForFinding,
} from './findingAggregation';
import { classifyFindingSourceKey } from './findingsSummaryUtils';
import { formatCategoryLabel, resourceGroupLabelFromRow } from './taxonomy';
import { serviceDisplayNameForRow, iconForRow } from '../config/assetIcons';
import { resourceTotalCost } from './costCurrency';
import { INVENTORY_API_PATH } from './resourceRowId';
import { toDisplayText } from './formatDisplay';

export const AC_FILTERS_STORAGE_KEY = 'action-centre-v2-filters';

export const DEFAULT_AC_FILTERS = {
  workflow: 'all',
  severity: 'all',
  source: 'all',
  type: 'all',
  search: '',
};

export const DEFAULT_AC_SORT = 'savings-desc';

const SEVERITY_CHIP_MAP = {
  CRITICAL: 'critical',
  HIGH: 'high',
  MEDIUM: 'medium',
  LOW: 'low',
};

const SOURCE_CHIP_MAP = {
  cost_performance: 'engine',
  reliability_security: 'advisor',
  governance: 'governance',
};

const SOURCE_CHIP_LABELS = {
  engine: 'Engine',
  advisor: 'Advisor',
  governance: 'Governance',
};

const WORKFLOW_CHIP_LABELS = {
  proposed: 'Proposed',
  approved: 'Approved',
  executed: 'Executed',
};

const TYPE_CHIP_LABELS = {
  vm: 'VM',
  disk: 'Disk',
  database: 'Database',
  storage: 'Storage',
  kubernetes: 'Kubernetes',
  network: 'Network',
};

const SEVERITY_SORT_ORDER = { critical: 4, high: 3, medium: 2, low: 1 };

export function encodeResourceRouteId(armId) {
  return encodeURIComponent(armId || '');
}

export function decodeResourceRouteId(encoded) {
  try {
    return decodeURIComponent(encoded || '');
  } catch {
    return encoded || '';
  }
}

export function inferTypeChip(row, finding) {
  const service = String(serviceDisplayNameForRow(row) || finding?.resource_type || '').toLowerCase();
  const arm = String(row?.id || row?.resource_id || finding?.resource_id || '').toLowerCase();
  if (service.includes('kubernetes') || arm.includes('/managedclusters/') || arm.includes('/agentpools/')) {
    return 'kubernetes';
  }
  if (service.includes('virtual machine') || arm.includes('/virtualmachines/')) return 'vm';
  if (service.includes('disk') || arm.includes('/disks/')) return 'disk';
  if (service.includes('database') || arm.includes('/sql/') || arm.includes('/documentdb/')) return 'database';
  if (service.includes('storage') || arm.includes('/storageaccounts/')) return 'storage';
  if (service.includes('network') || arm.includes('/network/') || arm.includes('/publicipaddresses/')) {
    return 'network';
  }
  return 'vm';
}

export function resolveWorkflowStatus(actions = []) {
  const statuses = actions.map((a) => String(a.workflow_status || 'proposed').toLowerCase());
  if (statuses.includes('executed') || statuses.includes('completed')) return 'executed';
  if (statuses.includes('approved')) return 'approved';
  return 'proposed';
}

export function mapSourceChip(finding) {
  const key = classifyFindingSourceKey(finding);
  return SOURCE_CHIP_MAP[key] || 'engine';
}

export function mapSeverityChip(severity) {
  const raw = toDisplayText(severity || 'MEDIUM');
  return SEVERITY_CHIP_MAP[String(raw === '—' ? 'MEDIUM' : raw).toUpperCase()] || 'medium';
}

export function categoryLabelForFinding(finding, row) {
  const category = formatCategoryLabel(finding?.category || finding?.category_label || 'OTHER');
  const typeLabel = serviceDisplayNameForRow(row) || finding?.resource_type || 'Resource';
  return `${typeLabel} · ${category}`;
}

export function buildFindingTableRow({
  finding,
  row,
  actions = [],
  currency = 'CAD',
  subscriptionLabel = '',
}) {
  if (!finding || typeof finding !== 'object') return null;

  const resourceId = normalizeArmId(finding?.resource_id || row?.id);
  if (!resourceId) return null;

  const workflow = resolveWorkflowStatus(actions);
  const source = mapSourceChip(finding);
  const severity = mapSeverityChip(finding?.severity);
  const savings = Number(
    finding?.estimated_monthly_savings_usd
    ?? finding?.monthly_savings_usd
    ?? finding?.savings_usd
    ?? finding?.estimated_savings_usd
    ?? 0,
  );
  const recommendationCount = recommendationCountForFinding(finding);
  const headline = topFindingHeadline(finding) || 'Review finding';
  const cost = row ? resourceTotalCost(row, currency) : 0;
  const type = inferTypeChip(row, finding);
  const iconKey = iconForRow(row || { type: finding?.resource_type }, { apiPath: INVENTORY_API_PATH });

  return {
    id: resourceId,
    findingId: finding?.id || finding?.finding_id || resourceId,
    resourceId,
    resource: row?.name || finding?.resource_name || 'Unknown resource',
    rg: resourceGroupLabelFromRow(row) || finding?.resource_group || '—',
    typeLabel: serviceDisplayNameForRow(row) || finding?.resource_type || '—',
    iconKey,
    severity,
    severityRaw: finding?.severity,
    source,
    workflow,
    type,
    category: toDisplayText(finding?.category || 'OTHER').toLowerCase(),
    categoryLabel: categoryLabelForFinding(finding, row),
    cost,
    savings,
    recommendation: aggregatedRecommendationHeadline(finding, headline),
    recommendationCount,
    recommendations: finding?.recommendations || finding?.child_findings || null,
    finding,
    row,
    actions,
    subscriptionLabel,
  };
}

export function buildFindingTableRows({
  findings = [],
  resourceById = new Map(),
  actionsByResource = new Map(),
  currency = 'CAD',
  subscriptionLabel = '',
}) {
  const rows = [];
  const seenResources = new Set();
  for (const finding of findings) {
    if (!finding || typeof finding !== 'object') continue;
    try {
      if (!isActionCentreFinding(finding)) continue;
      const key = normalizeArmId(finding.resource_id);
      if (!key || seenResources.has(key)) continue;
      seenResources.add(key);
      const row = resourceById.get(key);
      const actions = actionsByResource.get(key) || [];
      const built = buildFindingTableRow({
        finding,
        row,
        actions,
        currency,
        subscriptionLabel,
      });
      if (built) rows.push(built);
    } catch {
      /* skip malformed finding rows */
    }
  }
  return rows;
}

export function acHasActiveFilters(filters = DEFAULT_AC_FILTERS) {
  return filters.workflow !== 'all'
    || filters.severity !== 'all'
    || filters.source !== 'all'
    || filters.type !== 'all'
    || Boolean(filters.search?.trim());
}

export function filterFindingRows(rows, filters = DEFAULT_AC_FILTERS) {
  const q = (filters.search || '').trim().toLowerCase();
  return rows.filter((f) => {
    if (q) {
      const hay = `${f.resource} ${f.recommendation} ${f.rg} ${f.typeLabel}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (filters.workflow !== 'all' && f.workflow !== filters.workflow) return false;
    if (filters.severity !== 'all' && f.severity !== filters.severity) return false;
    if (filters.source !== 'all' && f.source !== filters.source) return false;
    if (filters.type !== 'all' && f.type !== filters.type) return false;
    return true;
  });
}

export function sortFindingRows(rows, sortKey = DEFAULT_AC_SORT) {
  const [key, dir] = sortKey.split('-');
  const asc = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (key === 'resource') return a.resource.localeCompare(b.resource) * asc;
    if (key === 'recommendation') return a.recommendation.localeCompare(b.recommendation) * asc;
    if (key === 'category') return (a.categoryLabel || '').localeCompare(b.categoryLabel || '') * asc;
    if (key === 'cost') return (a.cost - b.cost) * asc;
    if (key === 'severity') {
      return ((SEVERITY_SORT_ORDER[a.severity] || 0) - (SEVERITY_SORT_ORDER[b.severity] || 0)) * asc;
    }
    if (key === 'source') return (a.source || '').localeCompare(b.source || '') * asc;
    if (key === 'status') return (a.workflow || '').localeCompare(b.workflow || '') * asc;
    return (a.savings - b.savings) * asc;
  });
}

export function hasActionCentreData({ findings = [], summary } = {}) {
  const open = summary?.action_centre_open_findings
    ?? summary?.open_findings
    ?? summary?.open_count;
  if (open != null && Number(open) > 0) return true;
  return Array.isArray(findings) && findings.length > 0;
}

export function resolveActionCentreEmptyState({
  totalCount = 0,
  hasActiveFilters = false,
  analysisAt = null,
  syncStatus = null,
} = {}) {
  if (hasActiveFilters) return 'filtered';
  if (totalCount > 0) return null;
  const inventorySynced = syncStatus?.inventory?.last_synced_at || syncStatus?.subscriptions?.last_synced_at;
  if (!inventorySynced) return 'no_sync';
  if (!analysisAt) return 'no_analysis';
  return 'empty_queue';
}

export function computeIntelStrip({
  summary,
  visibleRows = [],
  hasActiveFilters = false,
  currency = 'CAD',
}) {
  const proposedFromRows = visibleRows.filter((r) => r.workflow === 'proposed').length;
  const proposed = Number(
    summary?.workflow?.proposed
    ?? summary?.proposed_actions
    ?? proposedFromRows,
  );
  const open = Number(
    summary?.action_centre_open_findings
    ?? summary?.open_findings
    ?? summary?.open_count
    ?? visibleRows.length,
  );
  const critical = Number(summary?.by_severity?.CRITICAL ?? summary?.critical_count ?? 0)
    || visibleRows.filter((r) => r.severity === 'critical').length;
  const totalSavings = Number(summary?.estimated_monthly_savings_usd ?? summary?.total_savings_usd ?? 0);
  const visibleSavings = visibleRows.reduce((sum, r) => sum + (Number(r.savings) || 0), 0);
  const savings = hasActiveFilters ? visibleSavings : (totalSavings || visibleSavings);

  return { proposed, open, critical, savings, currency };
}

export function parseAcFiltersFromSearchParams(searchParams) {
  const filters = { ...DEFAULT_AC_FILTERS };
  if (searchParams.get('hasAction') === '1' || searchParams.get('status') === 'proposed') {
    filters.workflow = 'proposed';
  }
  const workflow = searchParams.get('workflow');
  if (workflow) filters.workflow = workflow;
  const severity = searchParams.get('severity');
  if (severity) filters.severity = severity;
  const source = searchParams.get('source');
  if (source) filters.source = source;
  const type = searchParams.get('type') || searchParams.get('resourceType');
  if (type) {
    const typeMap = {
      vms: 'vm', disks: 'disk', storage: 'storage', aks: 'kubernetes', sql: 'database',
    };
    filters.type = typeMap[type] || type;
  }
  const search = searchParams.get('search');
  if (search) filters.search = search;
  return filters;
}

export function loadAcFiltersState() {
  try {
    const raw = sessionStorage.getItem(AC_FILTERS_STORAGE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    return {
      filters: { ...DEFAULT_AC_FILTERS, ...(saved.filters || {}) },
      sort: saved.sort || DEFAULT_AC_SORT,
    };
  } catch {
    return null;
  }
}

export function saveAcFiltersState(filters, sort) {
  try {
    sessionStorage.setItem(AC_FILTERS_STORAGE_KEY, JSON.stringify({ filters, sort }));
  } catch {
    /* ignore storage errors */
  }
}

export {
  SOURCE_CHIP_LABELS,
  WORKFLOW_CHIP_LABELS,
  TYPE_CHIP_LABELS,
  SEVERITY_CHIP_MAP,
};
