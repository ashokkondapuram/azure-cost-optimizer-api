/**
 * Canonical keys/labels for drawer Essentials deduplication.
 * Inventory essentials and ARM property rows are merged into one Essentials
 * section; matching keys are shown once.
 */

const OVERVIEW_ESSENTIAL_FACT_KEYS = new Set([
  'name',
  'location',
  'resourcegroup',
  'resource_group',
  'state',
  '_state',
  'sku',
  '_sku',
  'type',
  'provisioningstate',
  'provisioning_state',
  'azureservicename',
  'service_name',
  'tier',
  'accesstier',
  'access_tier',
  'kind',
  'vmsize',
  'vm_size',
  'size',
  'kubernetesversion',
  'kubernetes_version',
  'version',
  '_version',
  'nodecount',
  'node_count',
  '_nodecount',
  'poolcount',
  'pool_count',
  'nodeautoprovisioning',
  'node_auto_provisioning',
  'nodeprovisioningprofile',
  'syncedat',
  'lastsynced',
  // Disk overview (DiskPropertiesPanel + essentials)
  'disksizegb',
  'diskstate',
  'diskiopsreadwrite',
  'diskmbpsreadwrite',
  'managedby',
  'managedbyextended',
  'lastmanagedby',
  'lastownershipupdatetime',
  'provisioned_iops',
  'provisioned_mbps',
  'size_gb',
  'burstingenabled',
  // Application gateway summary counts
  'backendpools',
  'healthprobes',
  'listeners',
  'rules',
  'backendaddresspools',
  'httplisteners',
  'requestroutingrules',
]);

const OVERVIEW_ESSENTIAL_LABELS = new Set([
  'resource group',
  'status',
  'location',
  'subscription id',
  'sku',
  'type',
  'arm type',
  'service',
  'provisioning state',
  'tier',
  'kind',
  'size',
  'version',
  'kubernetes version',
  'nodes',
  'node auto provisioning',
  'node pools',
  'node pool count',
  'total node count',
  'last synced',
  'resource id',
  'disk state',
  'provisioned size',
  'provisioned iops',
  'provisioned throughput',
  'attached to',
  'created',
  'last ownership update',
  'backend pools',
  'health probes',
  'listeners',
  'rules',
]);

/** Map variant keys/labels to one canonical dedupe token. */
const ESSENTIAL_KEY_ALIASES = {
  resourcegroup: 'resourcegroup',
  resource_group: 'resourcegroup',
  _state: 'state',
  _sku: 'sku',
  _version: 'version',
  kubernetesversion: 'version',
  kubernetes_version: 'version',
  vmsize: 'size',
  vm_size: 'size',
  aksnodeautoprovisioning: 'nodeautoprovisioning',
  node_auto_provisioning: 'nodeautoprovisioning',
  nodeprovisioningprofile: 'nodeautoprovisioning',
  aksnodepools: 'poolcount',
  nodepools: 'poolcount',
  pool_count: 'poolcount',
  aksnodes: 'nodecount',
  nodes: 'nodecount',
  node_count: 'nodecount',
  _nodecount: 'nodecount',
  totalnodecount: 'nodecount',
  accesstier: 'tier',
  access_tier: 'tier',
  provisioningstate: 'provisioningstate',
  provisioning_state: 'provisioningstate',
  backendaddresspools: 'backendpools',
  httplisteners: 'listeners',
  requestroutingrules: 'rules',
  lastsynced: 'lastsynced',
  syncedat: 'lastsynced',
};

const ESSENTIAL_LABEL_ALIASES = {
  'resource group': 'resourcegroup',
  status: 'state',
  'kubernetes version': 'version',
  version: 'version',
  'node auto provisioning': 'nodeautoprovisioning',
  'node pools': 'poolcount',
  'node pool count': 'poolcount',
  nodes: 'nodecount',
  'total node count': 'nodecount',
  'vm size': 'size',
  size: 'size',
  'access tier': 'tier',
  tier: 'tier',
  'provisioning state': 'provisioningstate',
  'last synced': 'lastsynced',
  'backend pools': 'backendpools',
  'health probes': 'healthprobes',
  listeners: 'listeners',
  rules: 'rules',
  'disk state': 'diskstate',
};

function normalizePropertyKey(key) {
  return String(key || '').trim().toLowerCase().replace(/[._-]+/g, '');
}

function canonicalEssentialKey(rawKey) {
  const normalized = normalizePropertyKey(rawKey);
  if (!normalized) return '';
  if (ESSENTIAL_KEY_ALIASES[normalized]) return ESSENTIAL_KEY_ALIASES[normalized];
  if (OVERVIEW_ESSENTIAL_FACT_KEYS.has(normalized)) return normalized;
  return normalized;
}

function canonicalEssentialLabel(label) {
  const normalized = String(label || '').trim().toLowerCase();
  if (!normalized) return '';
  if (ESSENTIAL_LABEL_ALIASES[normalized]) return ESSENTIAL_LABEL_ALIASES[normalized];
  if (OVERVIEW_ESSENTIAL_LABELS.has(normalized)) return canonicalEssentialKey(normalized);
  return normalized;
}

/** Stable match key for deduplicating essentials and property rows. */
export function essentialsRowMatchKey(row) {
  if (!row) return '';

  const factKey = normalizePropertyKey(row.fact_key || row.key || '');
  if (factKey) {
    const canonical = canonicalEssentialKey(factKey);
    if (OVERVIEW_ESSENTIAL_FACT_KEYS.has(factKey) || ESSENTIAL_KEY_ALIASES[factKey]) {
      return canonical;
    }
    const leaf = String(row.fact_key || row.key || '').split('.').pop() || '';
    const leafCanonical = canonicalEssentialKey(leaf);
    if (leaf && (OVERVIEW_ESSENTIAL_FACT_KEYS.has(normalizePropertyKey(leaf)) || ESSENTIAL_KEY_ALIASES[normalizePropertyKey(leaf)])) {
      return leafCanonical;
    }
    return canonical;
  }

  return canonicalEssentialLabel(row.label);
}

/** Drop duplicate essentials rows by canonical match key (first wins). */
export function dedupeEssentialRows(rows = []) {
  const seen = new Set();
  const deduped = [];
  for (const row of rows) {
    if (!row?.label) continue;
    const matchKey = essentialsRowMatchKey(row);
    if (matchKey && seen.has(matchKey)) continue;
    if (matchKey) seen.add(matchKey);
    deduped.push(row);
  }
  return deduped;
}

/** True when a property key is part of the inventory essentials set. */
export function isOverviewEssentialKey(key) {
  const normalized = normalizePropertyKey(key);
  if (!normalized) return false;
  if (OVERVIEW_ESSENTIAL_FACT_KEYS.has(normalized)) return true;
  if (ESSENTIAL_KEY_ALIASES[normalized]) return true;
  const leaf = String(key || '').split('.').pop()?.toLowerCase() || '';
  const leafNormalized = normalizePropertyKey(leaf);
  return OVERVIEW_ESSENTIAL_FACT_KEYS.has(leafNormalized) || Boolean(ESSENTIAL_KEY_ALIASES[leafNormalized]);
}

/** True when a property row matches a known inventory essential field. */
export function isOverviewEssentialRow(row) {
  if (!row) return true;
  const factKey = row.fact_key || '';
  if (isOverviewEssentialKey(factKey)) return true;

  const label = String(row.label || '').trim().toLowerCase();
  if (OVERVIEW_ESSENTIAL_LABELS.has(label)) return true;

  return false;
}
