export function getResourceIconMeta(service = '', resourceType = '') {
  const s = String(service).toLowerCase();
  const t = String(resourceType).toLowerCase();

  if (s.includes('sql') || s.includes('database') || t.includes('sql')) {
    return { className: 'resource-icon--database', label: 'SQL' };
  }
  if (s.includes('kubernetes') || t.includes('containerservice') || t.includes('managedclusters')) {
    return { className: 'resource-icon--kubernetes', label: 'AKS' };
  }
  if (t.includes('disks') || s.includes('disk')) {
    return { className: 'resource-icon--disk', label: 'DSK' };
  }
  if (s.includes('storage') || t.includes('storageaccounts')) {
    return { className: 'resource-icon--storage', label: 'STG' };
  }
  if (s.includes('network') || t.includes('loadbalancers') || t.includes('publicipaddresses')) {
    return { className: 'resource-icon--network', label: 'LB' };
  }
  return { className: 'resource-icon--vm', label: 'VM' };
}
