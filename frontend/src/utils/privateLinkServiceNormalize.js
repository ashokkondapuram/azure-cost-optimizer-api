/** Private link service row enrichment — PLS uses connections + visibility, not ARM sku. */

import { toDisplayText } from './formatDisplay';

export function formatPrivateLinkServiceSummary(props) {
  if (!props) return '';
  const conns = props.privateEndpointConnections || [];
  const count = Array.isArray(conns) ? conns.length : 0;
  const connPart = count
    ? `${count} connection${count === 1 ? '' : 's'}`
    : 'No connections';
  const visibility = props.visibility;
  if (visibility) return `${connPart} · ${visibility}`;
  return connPart;
}

export function enrichPrivateLinkServiceRow(row) {
  const props = row?.properties || {};
  const summary = formatPrivateLinkServiceSummary(props);
  const connectionCount = Array.isArray(props.privateEndpointConnections)
    ? props.privateEndpointConnections.length
    : null;
  return {
    ...row,
    sku: summary || row.sku || '',
    connectionCount: connectionCount ?? row.connectionCount,
    plsSummary: summary || row.plsSummary,
  };
}

export function privateLinkServiceDisplaySummary(row) {
  const enriched = enrichPrivateLinkServiceRow(row);
  const text = enriched.plsSummary || enriched.sku;
  return toDisplayText(text);
}
