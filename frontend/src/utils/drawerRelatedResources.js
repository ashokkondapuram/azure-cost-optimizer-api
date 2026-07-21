import { normalizeArmResourceId, isArmResourceId, shortArmResourceLabel } from './armResourceLinks';
import { getDiskHostAttachment } from '../it-services/compute-disk/utils/diskUtils';

function resolveArmType(resource) {
  if (!resource) return '';
  const type = String(resource.type || '').toLowerCase();
  if (type.includes('/')) return type;
  const rid = String(resource.id || resource.resource_id || '').toLowerCase();
  if (rid.includes('/providers/')) {
    const parts = rid.split('/');
    const idx = parts.indexOf('providers');
    if (idx >= 0 && parts[idx + 2]) {
      return `${parts[idx + 1]}/${parts[idx + 2]}`.toLowerCase();
    }
  }
  return type;
}


function pushUnique(list, seen, entry) {
  const id = normalizeArmResourceId(entry?.id || '');
  if (!id || !isArmResourceId(id) || seen.has(id.toLowerCase())) return;
  seen.add(id.toLowerCase());
  list.push({
    id,
    label: entry.label || shortArmResourceLabel(id),
    relation: entry.relation || 'Related resource',
  });
}

function parentArmResourceId(resourceId, dropSegments = 2) {
  const parts = normalizeArmResourceId(resourceId).split('/').filter(Boolean);
  if (parts.length <= dropSegments + 4) return null;
  const parent = parts.slice(0, parts.length - dropSegments);
  const candidate = `/${parent.join('/')}`;
  return isArmResourceId(candidate) ? candidate : null;
}

function relatedFromFindings(findings = []) {
  const out = [];
  const seen = new Set();
  for (const finding of findings) {
    const ids = finding?.related_resource_ids || finding?.evidence?.related_resource_ids || [];
    for (const rawId of ids) {
      pushUnique(out, seen, {
        id: rawId,
        relation: 'Linked in finding',
      });
    }
  }
  return out;
}

function relatedFromDependencies(dependencies) {
  const out = [];
  const seen = new Set();
  for (const rawId of dependencies?.direct_outbound || []) {
    pushUnique(out, seen, { id: rawId, relation: 'Depends on' });
  }
  for (const rawId of dependencies?.direct_inbound || []) {
    pushUnique(out, seen, { id: rawId, relation: 'Used by' });
  }
  return out;
}

/** Resolve related resources for drawer Trends comparison charts. */
export function resolveRelatedResources(resource, {
  findings = [],
  dependencies = null,
  inventoryProperties = [],
} = {}) {
  if (!resource) return [];

  const rid = normalizeArmResourceId(resource.id || resource.resource_id || '');
  const seen = new Set([rid.toLowerCase()]);
  const related = [];

  relatedFromFindings(findings).forEach((entry) => pushUnique(related, seen, entry));
  relatedFromDependencies(dependencies).forEach((entry) => pushUnique(related, seen, entry));

  const armType = resolveArmType(resource).toLowerCase();
  const props = resource.properties || {};

  if (armType.includes('microsoft.compute/disks')) {
    const host = getDiskHostAttachment(resource);
    if (host?.armId) {
      pushUnique(related, seen, {
        id: host.armId,
        label: host.attachment?.displayLabel,
        relation: host.status === 'last_attached' ? 'Last attached VM' : 'Attached VM',
      });
    }
  }

  if (armType.includes('microsoft.compute/virtualmachines')) {
    const osDiskId = props?.storageProfile?.osDisk?.managedDisk?.id
      || props?.osDisk?.managedDisk?.id;
    if (osDiskId) {
      pushUnique(related, seen, { id: osDiskId, relation: 'OS disk' });
    }
  }

  if (armType.includes('microsoft.servicebus/namespaces/queues')
    || armType.includes('microsoft.servicebus/namespaces/topics')) {
    const namespaceId = parentArmResourceId(rid, 2);
    if (namespaceId) {
      pushUnique(related, seen, {
        id: namespaceId,
        label: shortArmResourceLabel(namespaceId),
        relation: 'Namespace',
      });
    }
  }

  if (armType.includes('microsoft.eventhub/namespaces/eventhubs')) {
    const namespaceId = parentArmResourceId(rid, 2);
    if (namespaceId) {
      pushUnique(related, seen, {
        id: namespaceId,
        label: shortArmResourceLabel(namespaceId),
        relation: 'Event Hubs namespace',
      });
    }
  }

  if (armType.includes('microsoft.sql/servers/databases')) {
    const serverId = parentArmResourceId(rid, 2);
    if (serverId) {
      pushUnique(related, seen, {
        id: serverId,
        label: shortArmResourceLabel(serverId),
        relation: 'SQL server',
      });
    }
  }

  for (const row of inventoryProperties || []) {
    const key = String(row?.fact_key || '').toLowerCase();
    if (!key.includes('managedby') && !key.includes('namespace') && !key.includes('server')) continue;
    const val = row?.value;
    if (typeof val === 'string' && isArmResourceId(val)) {
      pushUnique(related, seen, {
        id: val,
        relation: row.label || 'Inventory link',
      });
    }
  }

  return related;
}

export { trendMetricKeysForType, trendMetricKeysForResource } from './drawerTrendMetrics';

/** Extract numeric metric values from a batch-lookup metrics payload. */
export function metricValuesFromPayload(metricsData, metricKeys) {
  if (!metricsData) return {};
  const rows = [
    ...(metricsData.metrics || []),
    ...(metricsData.derived || []),
    ...(metricsData.facts ? Object.entries(metricsData.facts).map(([fact_key, value]) => ({
      fact_key,
      value,
    })) : []),
  ];
  const byKey = new Map(rows.map((row) => [String(row.fact_key || '').toLowerCase(), row]));
  const out = {};
  for (const spec of metricKeys) {
    const row = byKey.get(spec.factKey.toLowerCase());
    const stats = row?.stats || {};
    const primary = String(row?.primary_stat || '').toLowerCase();
    const raw = row?.value
      ?? (primary && stats[primary] != null ? stats[primary] : null)
      ?? stats.maximum
      ?? stats.total
      ?? stats.average
      ?? stats.minimum
      ?? null;
    const num = Number(raw);
    if (Number.isFinite(num)) {
      out[spec.factKey] = { ...spec, value: num };
    }
  }
  return out;
}
