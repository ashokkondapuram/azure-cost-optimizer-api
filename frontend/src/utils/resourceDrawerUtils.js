import { toDisplayText, formatPowerState } from './formatDisplay';
import { formatDateTime } from './format';
import { normalizeArmResourceId, isArmResourceId } from './armResourceLinks';
import { buildResourcePropertyGroups, filterDisplayablePropertyRows } from './resourcePropertyTabs';
import { dedupeEssentialRows, essentialsRowMatchKey } from './drawerOverviewDedupe';
import { enrichDrawerEssentials } from './drawerResourceTypeMetrics';
import { isApplicationGatewayResource, isApplicationGatewaySummaryPropertyKey } from './applicationGatewayPropertySummary';
import { isAnalysisEssentialRow } from './analysisEssentialProperties';
import { resolveDrawerCanonicalType } from './drawerTrendMetrics';

function addRow(rows, key, label, rawValue, extras = {}) {
  const value = toDisplayText(rawValue);
  if (!value || value === '—') return;
  rows.push({
    key,
    label,
    value,
    ...extras,
  });
}

const PROPERTY_ESSENTIALS = [
  ['Tier', ['tier', 'accessTier', 'access_tier']],
  ['Kind', ['kind']],
  ['Size', ['vmSize', 'vm_size', 'size', 'hardwareProfile.vmSize']],
  ['Version', ['kubernetesVersion', 'kubernetes_version', 'version']],
  ['Provisioning state', ['provisioningState', 'provisioning_state']],
];

function addPropertyEssentials(rows, properties, seenLabels, filterOptions = {}) {
  if (!properties || typeof properties !== 'object') return;
  for (const [label, keys] of PROPERTY_ESSENTIALS) {
    if (seenLabels.has(label)) continue;
    for (const key of keys) {
      const val = properties[key];
      if (val == null || val === '') continue;
      const candidate = { key: `prop-${label}`, label, value: toDisplayText(val), fact_key: key };
      if (!isAnalysisEssentialRow(candidate, filterOptions)) continue;
      addRow(rows, candidate.key, label, val, { fact_key: key });
      seenLabels.add(label);
      break;
    }
  }
}


function humanizeArmType(type) {
  const raw = String(type || '').trim();
  if (!raw) return '';
  const leaf = raw.includes('/') ? raw.split('/').pop() : raw;
  return leaf
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Azure portal–style essentials for the drawer Overview section. */
export function getDrawerEssentials(resource, { apiPath = '', metricsData = null } = {}) {
  if (!resource) return { summary: '', rows: [] };

  const rows = [];
  const seenLabels = new Set();
  const rid = normalizeArmResourceId(resource.id || resource.resource_id || '');

  const stateValue = resource.state || resource._state;
  if (stateValue) {
    addRow(rows, 'status', 'Status', formatPowerState(stateValue));
  }

  addRow(rows, 'sku', 'SKU', resource.sku || resource._sku);

  const armType = resource.type || '';
  if (armType) {
    addRow(rows, 'type', 'Type', humanizeArmType(armType));
  }

  const filterOptions = { resource, apiPath, canonicalType: resolveDrawerCanonicalType(resource, apiPath) };
  addPropertyEssentials(rows, resource.properties, seenLabels, filterOptions);
  enrichDrawerEssentials(rows, resource, seenLabels, apiPath, metricsData, {
    skipPoolSummary: (resource?._pools?.length || 0) > 0,
  });

  const presentKeys = new Set(rows.map((row) => essentialsRowMatchKey(row)).filter(Boolean));
  if (resource._version && !presentKeys.has('version')) {
    addRow(rows, 'version', 'Version', resource._version, { fact_key: 'version' });
  }
  if (resource._nodeCount != null && !presentKeys.has('nodecount')) {
    addRow(rows, 'nodes', 'Nodes', String(resource._nodeCount), { fact_key: 'node_count' });
  }
  if (resource.syncedAt) {
    addRow(rows, 'last-synced', 'Last synced', formatDateTime(resource.syncedAt));
  }

  if (rid && isArmResourceId(rid)) {
    rows.push({
      key: 'resource-id',
      label: 'Resource ID',
      value: rid,
      linkResourceId: rid,
      showFullId: true,
      fullWidth: true,
    });
  }

  return {
    summary: '',
    rows,
  };
}

function propertyRowToEssentialRow(row) {
  return {
    key: row.fact_key || row.label,
    label: row.label,
    value: row.formatted ?? row.value ?? '—',
  };
}

/**
 * Inventory essentials plus ARM/inventory properties, deduplicated within Essentials.
 * General scalar properties merge into the main essentials list; nested ARM objects
 * become titled subsections.
 */
export function buildCompleteDrawerEssentials(resource, inventoryProperties = [], { apiPath = '', metricsData = null } = {}) {
  const { summary, rows: baseRows } = getDrawerEssentials(resource, { apiPath, metricsData });
  const seen = new Set(
    baseRows.map((row) => essentialsRowMatchKey(row)).filter(Boolean),
  );
  const propertySections = [];
  const technicalPropertySections = [];
  const allPropertySections = [];
  const isAppGateway = isApplicationGatewayResource(resource, apiPath);
  const filterOptions = {
    resource,
    apiPath,
    canonicalType: resolveDrawerCanonicalType(resource, apiPath),
  };

  const propertyGroups = buildResourcePropertyGroups(resource, inventoryProperties);
  for (const group of propertyGroups) {
    const groupRows = [];
    const overflowRows = [];
    const sourceRows = isAppGateway && group.id === 'prop:general'
      ? group.rows.filter((row) => !isApplicationGatewaySummaryPropertyKey(row.fact_key))
      : group.rows;

    for (const row of filterDisplayablePropertyRows(sourceRows)) {
      const matchKey = essentialsRowMatchKey(row);
      if (matchKey && seen.has(matchKey)) continue;
      const essentialRow = propertyRowToEssentialRow(row);
      if (!isAnalysisEssentialRow({ ...row, ...essentialRow }, filterOptions)) {
        if (matchKey) seen.add(matchKey);
        overflowRows.push(essentialRow);
        continue;
      }
      if (matchKey) seen.add(matchKey);
      groupRows.push(essentialRow);
    }

    if (overflowRows.length) {
      allPropertySections.push({
        id: `${group.id}__overflow`,
        label: group.label,
        rows: overflowRows,
      });
    }
    if (!groupRows.length) continue;

    const section = {
      id: group.id,
      label: group.label,
      rows: groupRows,
    };

    if (isAppGateway && group.id !== 'prop:general') {
      technicalPropertySections.push(section);
      continue;
    }

    if (group.id === 'prop:general') {
      baseRows.push(...groupRows);
    } else {
      propertySections.push(section);
    }
  }

  return {
    summary,
    rows: dedupeEssentialRows(baseRows),
    propertySections,
    technicalPropertySections,
    allPropertySections,
  };
}

/** @deprecated Use getDrawerEssentials — kept for tests and disk tile adapters. */
export function getDrawerOverviewTiles(resource, options = {}) {
  const { rows } = getDrawerEssentials(resource, options);
  return rows.map((row, index) => ({
    key: row.key || `tile-${index}`,
    label: row.label,
    value: row.value,
    tone: row.tone,
    linkValue: row.linkResourceId,
    attachment: row.attachment,
  }));
}
