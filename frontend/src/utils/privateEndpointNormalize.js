/** Private endpoint row enrichment — PEs use connection target + state, not ARM sku. */

import { toDisplayText } from './formatDisplay';

function firstConnection(props) {
  if (!props) return null;
  for (const key of ['privateLinkServiceConnections', 'manualPrivateLinkServiceConnections']) {
    const conns = props[key] || [];
    if (Array.isArray(conns) && conns.length) {
      return conns[0];
    }
  }
  return null;
}

export function formatPrivateEndpointConnection(props) {
  const conn = firstConnection(props);
  if (!conn) return '';
  const inner = conn.properties && typeof conn.properties === 'object' ? conn.properties : conn;
  const groupId = inner.groupId;
  const targetId = inner.privateLinkServiceId || '';
  const targetName = targetId ? String(targetId).split('/').pop() : '';
  const label = groupId || targetName || '';
  const stateObj = inner.privateLinkServiceConnectionState;
  const state = (stateObj && typeof stateObj === 'object' ? stateObj.status : null)
    || inner.provisioningState
    || '';
  if (label && state) return `${label} · ${state}`;
  return label || state || '';
}

export function enrichPrivateEndpointRow(row) {
  const props = row?.properties || {};
  const connection = formatPrivateEndpointConnection(props);
  return {
    ...row,
    sku: connection || row.sku || '',
    connectionLabel: connection || row.connectionLabel,
  };
}

export function privateEndpointDisplayConnection(row) {
  const enriched = enrichPrivateEndpointRow(row);
  const text = enriched.connectionLabel || enriched.sku;
  return toDisplayText(text);
}
