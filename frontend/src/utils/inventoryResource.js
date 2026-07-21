/** True when the row is synced Azure inventory (not cost-export-only). */
export function isInventoryResource(row) {
  if (!row) return false;
  if (row.costExportOnly) return false;
  if (row.inInventory === false) return false;
  const type = String(row.type || row.resource_type || '').toLowerCase();
  if (type === 'compute/vmss') return false;
  const armId = String(row.id || row.resource_id || '').toLowerCase();
  if (armId.includes('/virtualmachinescalesets/')) return false;
  return true;
}
