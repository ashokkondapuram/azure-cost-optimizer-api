/**
 * Match billed inventory rows to Action centre resource-type deep links
 * (e.g. /action-centre?resourceType=appservices).
 */

import { COUNT_KEY_TO_CANONICAL, apiPathForCountKey } from '../config/resourceApiPaths';
import { createResourceMatcher } from '../it-services/_shared/createResourceMatcher';
import { normalizeCategory } from './taxonomy';

/** ARM path segments for rows that still carry provider types instead of canonical slugs. */
const ARM_PATH_HINTS = {
  'compute/vm': ['/virtualmachines/'],
  'compute/disk': ['/disks/'],
  'compute/snapshot': ['/snapshots/'],
  'compute/vmss': ['/virtualmachinescalesets/'],
  'containers/aks': ['/managedclusters/'],
  'containers/acr': ['/registries/'],
  'storage/account': ['/storageaccounts/'],
  'network/publicip': ['/publicipaddresses/'],
  'network/vnet': ['/virtualnetworks/'],
  'network/nic': ['/networkinterfaces/'],
  'network/nat': ['/natgateways/'],
  'network/loadbalancer': ['/loadbalancers/'],
  'network/appgateway': ['/applicationgateways/'],
  'network/nsg': ['/networksecuritygroups/'],
  'network/privateendpoint': ['/privateendpoints/'],
  'network/privatelinkservice': ['/privatelinkservices/'],
  'network/privatedns': ['/privatednszones/'],
  'database/sql': ['/microsoft.sql/servers/'],
  'database/cosmosdb': ['/documentdb/databaseaccounts/'],
  'database/postgresql': ['/microsoft.dbforpostgresql/'],
  'database/redis': ['/microsoft.cache/redis/'],
  'appservice/webapp': ['/sites/'],
  'appservice/plan': ['/serverfarms/'],
  'security/keyvault': ['/vaults/'],
  'monitoring/loganalytics': ['/operationalinsights/workspaces/'],
  'monitoring/appinsights': ['/insights/components/'],
  'integration/apim': ['/apimanagement/service/'],
  'integration/datafactory': ['/datafactories/'],
  'integration/logicapp': ['/logic/workflows/'],
  'messaging/eventhub': ['/eventhub/namespaces/'],
  'messaging/servicebus': ['/servicebus/namespaces/'],
  'analytics/databricks': ['/databricks/workspaces/'],
  'analytics/synapse': ['/synapse/workspaces/'],
  'analytics/adx': ['/kusto/clusters/'],
  'analytics/mlworkspace': ['/machinelearningservices/workspaces/'],
  'backup/recoveryvault': ['/recoveryservices/vaults/'],
  'search/cognitivesearch': ['/search/searchservices/'],
};

const matchersByCountKey = Object.fromEntries(
  Object.entries(COUNT_KEY_TO_CANONICAL).map(([countKey, canonical]) => [
    countKey,
    createResourceMatcher({
      apiPath: apiPathForCountKey(countKey),
      canonicalType: canonical,
    }),
  ]),
);

function pathMatchesCanonical(row, canonical) {
  const path = String(row?.id || row?.resource_id || '').toLowerCase();
  const hints = ARM_PATH_HINTS[canonical] || [];
  for (const hint of hints) {
    if (!path.includes(hint)) continue;
    if (canonical === 'compute/vm' && path.includes('/virtualmachinescalesets/')) return false;
    if (canonical === 'compute/disk' && path.includes('/snapshots/')) return false;
    return true;
  }
  return false;
}

/** True when a billed inventory row belongs to the given resource page definition. */
export function matchesActionCentreResourcePage(row, page) {
  if (!page?.countKey) return true;
  const canonical = COUNT_KEY_TO_CANONICAL[page.countKey];
  if (!canonical) return true;

  const matcher = matchersByCountKey[page.countKey];
  if (matcher?.(row)) return true;
  return pathMatchesCanonical(row, canonical);
}

/** Category chip filter — findings first, then inventory row category when analysis exists. */
export function matchesActionCentreCategory(row, rec, categoryKey) {
  if (!categoryKey) return true;
  const key = String(categoryKey).toUpperCase();
  if (rec?.findings?.some((f) => String(f.category || '').toUpperCase() === key)) return true;
  if (String(rec?.topFinding?.category || '').toUpperCase() === key) return true;
  const rowCategory = normalizeCategory(row?.category);
  if (rowCategory === key && (rec?.hasRecommendations || Number(row?.analysisFindingsCount) > 0)) {
    return true;
  }
  return false;
}
