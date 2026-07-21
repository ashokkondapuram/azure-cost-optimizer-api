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

/** Unified Action centre deep link for any ARM resource. */
export function actionCentreLink(resourceId, { section, inspect = false } = {}) {
  const rid = normalizeArmResourceId(resourceId);
  if (!isArmResourceId(rid)) return null;
  const params = new URLSearchParams();
  params.set('resource', rid);
  if (inspect) params.set('inspect', '1');
  if (section) params.set('section', section);
  return `/action-centre?${params.toString()}`;
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

/** Legacy inventory route — redirects to Action centre via ResourceRoutes. */
export function appRouteForResourceId(resourceId) {
  return actionCentreLink(resourceId);
}

/** Action centre link that opens full analysis for a resource. */
export function inventoryInspectLink(resourceId, { section = 'advanced-analysis' } = {}) {
  return actionCentreLink(resourceId, { section, inspect: true });
}

/** Map insight drawer section id to Action centre URL section param. */
export function drawerSectionToHubSection(sectionId) {
  const map = {
    analysis: 'advanced-analysis',
    properties: 'technical-properties',
    metrics: 'vm-metrics',
    actions: 'proposed-actions',
    'cost-drivers': 'cost-drivers',
    trends: 'trends',
  };
  if (String(sectionId || '').startsWith('prop:')) return 'technical-properties';
  return map[sectionId] || null;
}

/** Action centre link that mirrors the open insight drawer (same resource + section). */
export function actionCentreHubLink(resourceId, { sectionId } = {}) {
  const section = drawerSectionToHubSection(sectionId);
  return actionCentreLink(resourceId, { inspect: true, section: section || undefined });
}

/** Resolve any app href (legacy or new) to Action centre when possible. */
export function resolveResourceAppHref(finding) {
  if (!finding) return null;
  if (finding.resource_id) {
    return actionCentreLink(finding.resource_id, { inspect: true, section: 'advanced-analysis' });
  }
  const href = finding.resource_app_href;
  if (!href) return null;
  if (href.startsWith('/action-centre')) return href;
  return href;
}
