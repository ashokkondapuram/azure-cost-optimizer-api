/** Resolve display SKU from row fields or nested properties (App Gateway, Firewall, PE, etc.). */

import { formatPrivateEndpointConnection } from './privateEndpointNormalize';
import { formatPrivateLinkServiceSummary } from './privateLinkServiceNormalize';
import { formatPrivateDnsZoneSummary } from './privateDnsNormalize';
import { formatAppServicePlanSku, formatAppServiceWebappSku } from './appServiceNormalize';

export function resolveResourceSku(row) {
  const top = row?.sku;
  if (top != null && top !== '') {
    return typeof top === 'object' ? (top.name || top.tier || null) : top;
  }
  if (row?.type === 'network/privateendpoint' || row?.properties?.privateLinkServiceConnections) {
    const peLabel = formatPrivateEndpointConnection(row.properties);
    if (peLabel) return peLabel;
  }
  if (row?.type === 'network/privatelinkservice' || row?.properties?.privateEndpointConnections) {
    const plsLabel = formatPrivateLinkServiceSummary(row.properties);
    if (plsLabel) return plsLabel;
  }
  if (
    row?.type === 'network/privatedns'
    || row?.properties?.numberOfRecordSets != null
    || row?.properties?.zoneType
  ) {
    const dnsLabel = formatPrivateDnsZoneSummary(row.properties);
    if (dnsLabel) return dnsLabel;
  }
  if (row?.type === 'appservice/plan') {
    const planLabel = formatAppServicePlanSku(row);
    if (planLabel) return planLabel;
  }
  if (row?.type === 'appservice/webapp' || row?.properties?.serverFarmId) {
    const appLabel = formatAppServiceWebappSku(row);
    if (appLabel) return appLabel;
  }
  const nested = row?.properties?.sku;
  if (!nested) return null;
  if (typeof nested === 'string') return nested;
  return nested.name || nested.tier || null;
}
