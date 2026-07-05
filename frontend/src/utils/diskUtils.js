/** Disk helpers retained for tests and internal analysis paths (not dashboard inventory). */

export function isDiskResource(resource, apiPath = '') {
  const type = (resource?.type || '').toLowerCase();
  if (type.includes('disk') && !type.includes('snapshot')) return true;
  return String(apiPath || '').includes('/disks');
}

export function diskLastOwnershipUpdate(resource) {
  if (!resource) return null;
  return resource.properties?.lastOwnershipUpdateTime || null;
}
