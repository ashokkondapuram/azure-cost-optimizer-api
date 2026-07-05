/** Virtual network row enrichment — VNets use address space, not ARM sku. */

import { toDisplayText } from './formatDisplay';

export function formatVnetAddressSpace(props) {
  if (!props) return '';
  const prefixes = props?.addressSpace?.addressPrefixes || [];
  if (!prefixes.length) return '';
  const shown = prefixes.slice(0, 2).join(', ');
  if (prefixes.length > 2) return `${shown} (+${prefixes.length - 2})`;
  return shown;
}

export function enrichVnetRow(row) {
  const props = row?.properties || {};
  const addressSpace = formatVnetAddressSpace(props);
  const subnetCount = Array.isArray(props.subnets) ? props.subnets.length : null;
  const sku = addressSpace || row.sku || '';
  return {
    ...row,
    sku: sku || row.sku,
    addressSpace: addressSpace || row.addressSpace,
    subnetCount: subnetCount ?? row.subnetCount,
  };
}

export function vnetDisplaySku(row) {
  const enriched = enrichVnetRow(row);
  const text = enriched.addressSpace || enriched.sku;
  return toDisplayText(text);
}
