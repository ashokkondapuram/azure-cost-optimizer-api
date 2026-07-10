import { CANONICAL_TYPE } from '../drawer';

const DISK_EVIDENCE_METRIC_IDS = new Set([
  'disk_state',
  'size_gb',
  'provisioned_iops',
  'provisioned_mbps',
  'managed_by',
  'last_managed_by',
  'time_created',
  'last_ownership_update',
]);

function isDiskContext(inventoryContext) {
  return Boolean(
    inventoryContext?.diskPropertiesShown
    || inventoryContext?.canonicalType === CANONICAL_TYPE,
  );
}

/** Add disk metric ids to hide when the drawer properties panel already shows them. */
export function enrichEvidenceFilter(hideIds, inventoryContext) {
  if (!isDiskContext(inventoryContext)) return;

  for (const id of DISK_EVIDENCE_METRIC_IDS) {
    hideIds.add(id);
  }
}
