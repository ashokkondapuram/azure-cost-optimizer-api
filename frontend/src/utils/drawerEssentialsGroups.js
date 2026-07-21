/**
 * Organize drawer essentials into Azure portal–style property groups.
 * Empty groups are omitted from the returned list.
 */

import { essentialsRowMatchKey } from './drawerOverviewDedupe';

const GROUP_ORDER = ['identity', 'status', 'configuration', 'networking', 'cost', 'additional'];

const STANDARD_GROUP_IDS = new Set(GROUP_ORDER);

const MAX_MERGED_ROWS = 5;
const MERGE_CANDIDATE_MAX_ROWS = 3;

const GROUP_LABELS = {
  identity: 'Identity',
  status: 'Status',
  configuration: 'Configuration',
  networking: 'Networking',
  cost: 'Cost',
  additional: 'Additional',
};

/** Actionable fields surface first within each group card. */
const ROW_PRIORITY = {
  identity: ['type', 'name', 'resourceid', 'service', 'armtype', 'canonicaltype'],
  status: [
    'powerstate', 'status', 'state', 'diskstate', 'provisioningstate',
    'health', 'availability', 'lastsynced',
  ],
  configuration: [
    'sku', 'tier', 'kind', 'size', 'vmsize', 'disksizegb', 'attached', 'attachedto',
    'capacity', 'iops', 'throughput', 'diskiops', 'diskmbps', 'bursting',
    'version', 'nodes', 'count', 'scale', 'os', 'image',
  ],
  networking: [
    'managedby', 'attachedto', 'attached', 'ipaddress', 'publicip', 'privateip',
    'vnet', 'subnet', 'fqdn', 'dns', 'endpoint', 'hostname',
  ],
  cost: ['cost', 'monthly', 'billing', 'savings', 'accesstier', 'pricing', 'spend'],
};

function normalizeToken(value) {
  return String(value || '').trim().toLowerCase().replace(/[._\s-]+/g, '');
}

function rowTokens(row) {
  const tokens = new Set();
  const key = normalizeToken(row?.key);
  const factKey = normalizeToken(row?.fact_key);
  const label = normalizeToken(row?.label);
  if (key) tokens.add(key);
  if (factKey) tokens.add(factKey);
  if (label) tokens.add(label);
  const leaf = String(row?.fact_key || row?.key || '').split('.').pop();
  if (leaf) tokens.add(normalizeToken(leaf));
  return tokens;
}

function tokensMatchAny(tokens, patterns) {
  for (const pattern of patterns) {
    const normalized = normalizeToken(pattern);
    if (!normalized) continue;
    if (tokens.has(normalized)) return true;
    for (const token of tokens) {
      if (token.includes(normalized) || normalized.includes(token)) return true;
    }
  }
  return false;
}

const GROUP_MATCHERS = {
  identity: [
    'resourceid', 'resource-id', 'name', 'type', 'armtype', 'service',
    'azureservicename', 'canonicaltype', 'resource name',
  ],
  status: [
    'status', 'state', 'diskstate', 'disk-state', 'provisioningstate',
    'provisioning-state', 'powerstate', 'lastsynced', 'last-synced',
    'disk state', 'provisioning state', 'health', 'availability',
  ],
  configuration: [
    'sku', 'tier', 'kind', 'size', 'version', 'nodes', 'vmsize', 'vm-size',
    'disksizegb', 'disk-size', 'diskiops', 'diskmbps', 'bursting', 'capacity',
    'kubernetesversion', 'nodeautoprovisioning', 'nodeprovisioningprofile', 'os', 'image', 'generation', 'redundancy',
    'backendpools', 'healthprobes', 'listeners', 'rules', 'replication',
    'encryption', 'https', 'ssl', 'mode', 'count', 'scale', 'throughput',
    'iops', 'provisioned', 'attached', 'hardwareprofile',
  ],
  networking: [
    'managedby', 'managed-by', 'attachedto', 'attached-to', 'ipaddress',
    'publicip', 'privateip', 'vnet', 'subnet', 'fqdn', 'dns', 'endpoint',
    'frontend', 'backendaddress', 'network', 'hostname', 'port', 'listener',
    'nat', 'gateway', 'nic', 'loadbalancer',
  ],
  cost: [
    'cost', 'price', 'billing', 'savings', 'monthly', 'currency', 'spend',
    'accesstier', 'access-tier', 'pricing',
  ],
};

/**
 * @param {object} row — essentials row ({ key, label, value, ... })
 * @returns {string} group id
 */
export function classifyEssentialRow(row) {
  const tokens = rowTokens(row);

  if (tokensMatchAny(tokens, ['accesstier', 'access-tier', 'access tier'])) {
    return 'cost';
  }

  for (const groupId of GROUP_ORDER) {
    if (groupId === 'additional') continue;
    if (tokensMatchAny(tokens, GROUP_MATCHERS[groupId])) return groupId;
  }

  return 'additional';
}

function rowPriorityIndex(row, groupId) {
  const priorities = ROW_PRIORITY[groupId];
  if (!priorities?.length) return 999;
  const tokens = rowTokens(row);
  for (let index = 0; index < priorities.length; index += 1) {
    if (tokensMatchAny(tokens, [priorities[index]])) return index;
  }
  return priorities.length;
}

function sortGroupRows(rows, groupId) {
  return [...rows].sort((left, right) => {
    const priorityDiff = rowPriorityIndex(left, groupId) - rowPriorityIndex(right, groupId);
    if (priorityDiff !== 0) return priorityDiff;
    return String(left.label || '').localeCompare(String(right.label || ''));
  });
}

function isStandardGroup(group) {
  return STANDARD_GROUP_IDS.has(group?.id);
}

function groupHasResourceId(group) {
  return (group?.rows || []).some((row) => row.key === 'resource-id');
}

function cloneGroup(group, overrides = {}) {
  return {
    ...group,
    rows: [...(group.rows || [])],
    ...overrides,
  };
}

/**
 * Merge single-row standard groups with neighbors so the Overview grid stays balanced.
 * ARM / nested sections are left intact; groups containing Resource ID span full width.
 * @param {{ id: string, label: string, rows: object[] }[]} groups
 * @returns {{ id: string, label: string, rows: object[], spanFull?: boolean }[]}
 */
export function packEssentialGroups(groups = []) {
  if (groups.length < 2) {
    return groups.map((group) => ({
      ...group,
      spanFull: groupHasResourceId(group),
    }));
  }

  const packed = [];
  let index = 0;

  while (index < groups.length) {
    const current = groups[index];

    if (!isStandardGroup(current) || current.rows.length >= 2) {
      packed.push(cloneGroup(current));
      index += 1;
      continue;
    }

    const next = groups[index + 1];
    if (
      next
      && isStandardGroup(next)
      && next.rows.length <= MERGE_CANDIDATE_MAX_ROWS
      && current.rows.length + next.rows.length <= MAX_MERGED_ROWS
    ) {
      packed.push(cloneGroup(current, {
        id: `${current.id}__${next.id}`,
        label: `${current.label} & ${next.label}`,
        rows: [...current.rows, ...next.rows],
      }));
      index += 2;
      continue;
    }

    const previous = packed[packed.length - 1];
    if (
      previous
      && isStandardGroup(previous)
      && previous.rows.length <= MERGE_CANDIDATE_MAX_ROWS
      && current.rows.length + previous.rows.length <= MAX_MERGED_ROWS
    ) {
      previous.rows = [...previous.rows, ...current.rows];
      previous.id = `${previous.id}__${current.id}`;
      previous.label = `${previous.label} & ${current.label}`;
      index += 1;
      continue;
    }

    packed.push(cloneGroup(current));
    index += 1;
  }

  return packed.map((group) => ({
    ...group,
    spanFull: groupHasResourceId(group),
  }));
}

/**
 * Merge base rows, property sections, and nested ARM sections into grouped essentials.
 * Nested ARM sections (e.g. Application Gateway listeners) render as labeled group cards
 * so every synced property stays visible without toggles.
 * @param {{ rows?: object[], propertySections?: object[], technicalPropertySections?: object[] }} essentials
 * @returns {{ id: string, label: string, rows: object[] }[]}
 */
export function organizeEssentialsIntoGroups(essentials = {}) {
  const allRows = [];
  const seen = new Set();

  const pushRow = (row) => {
    if (!row?.label) return;
    const dedupeKey = essentialsRowMatchKey(row);
    if (dedupeKey && seen.has(dedupeKey)) return;
    if (dedupeKey) seen.add(dedupeKey);
    allRows.push(row);
  };

  for (const row of essentials.rows || []) pushRow(row);
  for (const section of essentials.propertySections || []) {
    for (const row of section.rows || []) pushRow(row);
  }

  const buckets = Object.fromEntries(GROUP_ORDER.map((id) => [id, []]));
  for (const row of allRows) {
    const groupId = classifyEssentialRow(row);
    buckets[groupId].push(row);
  }

  const groups = GROUP_ORDER
    .filter((id) => buckets[id].length > 0)
    .map((id) => ({
      id,
      label: GROUP_LABELS[id],
      rows: sortGroupRows(buckets[id], id),
    }));

  for (const section of essentials.technicalPropertySections || []) {
    const sectionRows = (section.rows || []).filter((row) => row?.label);
    if (!sectionRows.length) continue;
    groups.push({
      id: section.id || `arm-section-${groups.length}`,
      label: section.label || 'Properties',
      rows: sectionRows,
    });
  }

  return packEssentialGroups(groups);
}
