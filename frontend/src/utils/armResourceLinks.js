/** Detect and format Azure ARM resource IDs for compact linked display. */

const ARM_RESOURCE_ID_PATTERN = /^\/?subscriptions\/[^/]+\/resourcegroups\/[^/]+\/providers\/[^/]+\/[^/]+\/[^/]+/i;

export function isArmResourceId(value) {
  if (typeof value !== 'string') return false;
  return ARM_RESOURCE_ID_PATTERN.test(value.trim());
}

export function normalizeArmResourceId(resourceId) {
  const trimmed = String(resourceId || '').trim();
  if (!trimmed) return '';
  return trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
}

function armPathParts(resourceId) {
  return normalizeArmResourceId(resourceId).split('/').filter(Boolean);
}

/** Classify a compute host ARM id (VM, VMSS, or VMSS instance) attached to a disk. */
export function parseComputeHostAttachment(resourceId) {
  const rid = normalizeArmResourceId(resourceId);
  if (!isArmResourceId(rid)) return null;

  const parts = armPathParts(rid);
  const providersIdx = parts.findIndex((part) => part.toLowerCase() === 'providers');
  if (providersIdx < 0 || providersIdx + 3 >= parts.length) return null;

  const providerNamespace = `${parts[providersIdx + 1]}/${parts[providersIdx + 2]}`.toLowerCase();
  const resourceName = parts[providersIdx + 3];

  if (providerNamespace === 'microsoft.compute/virtualmachines') {
    return {
      kind: 'vm',
      resourceId: rid,
      name: resourceName,
      typeLabel: 'Virtual machine',
      displayLabel: resourceName,
      inventoryLink: inventoryInspectLink(rid),
      portalLink: azurePortalUrl(rid),
    };
  }

  if (providerNamespace === 'microsoft.compute/virtualmachinescalesets') {
    const vmssParentId = `/${parts.slice(0, providersIdx + 4).join('/')}`;
    const isInstance = parts[providersIdx + 4]?.toLowerCase() === 'virtualmachines'
      && parts[providersIdx + 5] != null
      && parts[providersIdx + 5] !== '';

    if (isInstance) {
      const instanceId = parts[providersIdx + 5];
      return {
        kind: 'vmss_instance',
        resourceId: rid,
        parentResourceId: vmssParentId,
        name: resourceName,
        instanceId,
        typeLabel: 'Scale set instance',
        displayLabel: `${resourceName} / instance ${instanceId}`,
        inventoryLink: inventoryInspectLink(vmssParentId),
        portalLink: azurePortalUrl(rid),
        scaleSetLabel: resourceName,
        scaleSetInventoryLink: inventoryInspectLink(vmssParentId),
        scaleSetPortalLink: azurePortalUrl(vmssParentId),
      };
    }

    return {
      kind: 'vmss',
      resourceId: rid,
      name: resourceName,
      typeLabel: 'VM scale set',
      displayLabel: resourceName,
      inventoryLink: inventoryInspectLink(rid),
      portalLink: azurePortalUrl(rid),
    };
  }

  return null;
}

export function shortArmResourceLabel(resourceId) {
  const normalized = normalizeArmResourceId(resourceId);
  if (!normalized) return '';
  const parts = normalized.split('/').filter(Boolean);
  return parts[parts.length - 1] || normalized;
}

export function azurePortalUrl(resourceId) {
  if (!isArmResourceId(resourceId)) return null;
  return `https://portal.azure.com/#resource${normalizeArmResourceId(resourceId)}`;
}

const ARM_PROVIDER_TO_APP_PATH = {
  'microsoft.compute/virtualmachines': '/vms',
  'microsoft.compute/virtualmachinescalesets': '/vmss',
  'microsoft.compute/disks': '/disks',
  'microsoft.compute/snapshots': '/snapshots',
  'microsoft.containerservice/managedclusters': '/aks',
  'microsoft.containerregistry/registries': '/acr',
  'microsoft.web/sites': '/appservices',
  'microsoft.web/serverfarms': '/appserviceplans',
  'microsoft.storage/storageaccounts': '/storage',
  'microsoft.network/publicipaddresses': '/publicips',
  'microsoft.network/virtualnetworks': '/vnets',
  'microsoft.network/networkinterfaces': '/nics',
  'microsoft.network/natgateways': '/natgateways',
  'microsoft.network/loadbalancers': '/loadbalancers',
  'microsoft.network/applicationgateways': '/appgateways',
  'microsoft.network/networksecuritygroups': '/nsgs',
  'microsoft.network/privateendpoints': '/privateendpoints',
  'microsoft.network/privatelinkservices': '/privatelinkservices',
  'microsoft.network/privatednszones': '/privatedns',
  'microsoft.sql/servers': '/sql',
  'microsoft.documentdb/databaseaccounts': '/cosmosdb',
  'microsoft.dbforpostgresql/flexibleservers': '/postgresql',
  'microsoft.cache/redis': '/redis',
  'microsoft.keyvault/vaults': '/keyvaults',
};

/** Best-effort inventory route for an ARM resource id. */
export function appRouteForResourceId(resourceId) {
  const rid = normalizeArmResourceId(resourceId).toLowerCase().replace(/\/+$/, '');
  const marker = '/providers/';
  const idx = rid.indexOf(marker);
  if (idx < 0) return null;
  const tail = rid.slice(idx + marker.length);
  const parts = tail.split('/');
  if (parts.length < 2) return null;
  const providerKey = `${parts[0]}/${parts[1]}`;
  const base = ARM_PROVIDER_TO_APP_PATH[providerKey];
  if (!base) return null;
  const name = parts[parts.length - 1];
  return name ? `${base}?search=${encodeURIComponent(name)}` : base;
}

/** Inventory route that opens the resource drawer on the advanced analysis section. */
export function inventoryInspectLink(resourceId, { section = 'advanced-analysis' } = {}) {
  const route = appRouteForResourceId(resourceId);
  if (!route) return null;
  const [path, query = ''] = route.split('?');
  const params = new URLSearchParams(query);
  params.set('inspect', '1');
  params.set('resourceId', normalizeArmResourceId(resourceId));
  if (section) params.set('section', section);
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}
