/**
 * Logical icon keys for pages, routes, and API paths.
 * Icons render via react-az-icons (open source).
 */
import {
  iconKeyFromResourceId,
  iconKeyForAzureType,
  iconKeyForCanonicalType,
  iconKeyForServiceName,
  iconKeyForApiPath,
} from './azureIconRegistry';

export {
  PAGE_ICON_KEYS as PAGE_ICONS,
  NAV_GROUP_KEYS as NAV_GROUP_ICONS,
  CATEGORY_KEYS as CATEGORY_ICONS,
  ARM_TYPE_KEYS as AZURE_TYPE_ICONS,
  CANONICAL_TYPE_KEYS,
  ROUTE_ICON_KEYS as ROUTE_ICONS,
  API_PATH_KEYS as API_PATH_ICONS,
  iconKeyForAzureType as iconForAzureType,
  iconKeyForCanonicalType as iconForCanonicalType,
  iconKeyForServiceName as iconForServiceName,
  iconKeyForCategory as iconForCategory,
  iconKeyForComponent as iconForComponent,
  iconKeyForRoute as iconForRoute,
  iconKeyForApiPath as iconForApiPath,
  iconKeyFromResourceId as iconFromResourceId,
  validateIconRegistry,
} from './azureIconRegistry';

export function iconForRow(row, { apiPath, fallback } = {}) {
  const props = row?.properties || {};
  const armType = props.armResourceType || props.arm_resource_type || row?.armResourceType;

  return (
    iconKeyFromResourceId(row?.resource_id || row?.id)
    || iconKeyForAzureType(armType)
    || iconKeyForCanonicalType(row?.type)
    || iconKeyForServiceName(row?.azureServiceName || row?.service_name)
    || iconKeyForApiPath(apiPath)
    || fallback
    || 'default'
  );
}

/** Human-readable resource type for drawer headers and finding context. */
export const CANONICAL_TYPE_LABELS = {
  'compute/vm': 'Virtual machine',
  'compute/vmss': 'Virtual machine scale set',
  'compute/disk': 'Managed disk',
  'compute/snapshot': 'Disk snapshot',
  'containers/aks': 'AKS cluster',
  'containers/acr': 'Container registry',
  'containers/aci': 'Container instance',
  'storage/account': 'Storage account',
  'network/publicip': 'Public IP address',
  'network/vnet': 'Virtual network',
  'network/nic': 'Network interface',
  'network/nat': 'NAT gateway',
  'network/loadbalancer': 'Load balancer',
  'network/appgateway': 'Application gateway',
  'network/nsg': 'Network security group',
  'network/privateendpoint': 'Private endpoint',
  'network/privatelinkservice': 'Private link service',
  'network/privatedns': 'Private DNS zone',
  'database/sql': 'SQL server',
  'database/cosmosdb': 'Cosmos DB account',
  'database/postgresql': 'PostgreSQL server',
  'database/redis': 'Redis cache',
  'appservice/webapp': 'App Service',
  'appservice/plan': 'App Service plan',
  'security/keyvault': 'Key vault',
  'monitoring/loganalytics': 'Log Analytics workspace',
  'monitoring/appinsights': 'Application Insights',
  'integration/apim': 'API Management',
  'integration/datafactory': 'Data factory',
  'integration/logicapp': 'Logic App',
  'messaging/eventhub': 'Event Hubs namespace',
  'messaging/servicebus': 'Service Bus namespace',
  'analytics/databricks': 'Databricks workspace',
  'analytics/synapse': 'Synapse workspace',
  'analytics/adx': 'Data Explorer cluster',
  'backup/recoveryvault': 'Recovery Services vault',
  'search/cognitivesearch': 'AI Search service',
};

const ARM_ID_TYPE_LABELS = [
  ['/microsoft.containerregistry/registries/', 'Container registry'],
  ['/microsoft.containerservice/managedclusters/', 'AKS cluster'],
  ['/microsoft.containerinstance/containergroups/', 'Container instance'],
  ['/microsoft.compute/virtualmachines/', 'Virtual machine'],
  ['/microsoft.compute/virtualmachinescalesets/', 'Virtual machine scale set'],
  ['/microsoft.compute/disks/', 'Managed disk'],
  ['/microsoft.compute/snapshots/', 'Disk snapshot'],
  ['/microsoft.storage/storageaccounts/', 'Storage account'],
  ['/microsoft.web/sites/', 'App Service'],
  ['/microsoft.web/serverfarms/', 'App Service plan'],
  ['/microsoft.network/virtualnetworks/', 'Virtual network'],
  ['/microsoft.network/networkinterfaces/', 'Network interface'],
  ['/microsoft.network/privateendpoints/', 'Private endpoint'],
  ['/microsoft.network/privatelinkservices/', 'Private link service'],
  ['/microsoft.network/privatednszones/', 'Private DNS zone'],
  ['/microsoft.billingbenefits/savingsplanorders/', 'Savings plan order'],
  ['/microsoft.billingbenefits/reservationorders/', 'Reservation order'],
];

/** Component / billing labels keyed by canonical resource type (mirrors component_map.py). */
export const CANONICAL_TO_SERVICE_LABEL = {
  'compute/vm': 'Virtual Machines',
  'compute/vmss': 'Virtual Machine Scale Sets',
  'compute/disk': 'Managed Disks',
  'compute/snapshot': 'Disk Snapshots',
  'appservice/webapp': 'App Service',
  'appservice/plan': 'App Service',
  'containers/aks': 'AKS',
  'containers/acr': 'Container Registry',
  'containers/aci': 'Container Instances',
  'storage/account': 'Storage Accounts',
  'network/publicip': 'Public IPs',
  'network/nic': 'Network Interfaces',
  'network/nat': 'NAT Gateways',
  'network/nsg': 'Network Security Groups',
  'network/loadbalancer': 'Load Balancers',
  'network/appgateway': 'Application Gateways',
  'network/vnet': 'Networking Extended',
  'network/privateendpoint': 'Networking Extended',
  'network/privatelinkservice': 'Networking Extended',
  'network/privatedns': 'Networking Extended',
  'network/firewall': 'Networking',
  'network/cdn': 'Networking',
  'database/sql': 'SQL Database',
  'database/postgresql': 'PostgreSQL',
  'database/cosmosdb': 'Cosmos DB',
  'database/redis': 'Redis Cache',
  'security/keyvault': 'Key Vault',
  'monitoring/loganalytics': 'Monitoring',
  'monitoring/appinsights': 'Monitoring',
  'integration/apim': 'Integration',
  'integration/datafactory': 'Integration',
  'integration/logicapp': 'Integration',
  'messaging/eventhub': 'Messaging',
  'messaging/servicebus': 'Messaging',
  'analytics/databricks': 'Analytics',
  'analytics/synapse': 'Analytics',
  'analytics/adx': 'Analytics',
  'analytics/mlworkspace': 'Analytics',
  'backup/recoveryvault': 'Backup',
  'search/cognitivesearch': 'Search',
};

export function resourceLabelForRow(row) {
  if (!row) return '';
  const canonical = (row.type || '').trim().toLowerCase();
  if (CANONICAL_TYPE_LABELS[canonical]) return CANONICAL_TYPE_LABELS[canonical];

  const rid = (row.id || row.resource_id || '').toLowerCase();
  for (const [fragment, label] of ARM_ID_TYPE_LABELS) {
    if (rid.includes(fragment)) return label;
  }

  return '';
}

/** Service column label — billing name when present, else canonical / ARM fallback. */
export function serviceDisplayNameForRow(row) {
  if (!row) return '';
  const billing = row.azureServiceName || row.service_name || row.billingServiceName;
  if (billing && String(billing).trim()) return String(billing).trim();

  const canonical = String(row.type || row.canonical_type || row.resource_type || '').trim().toLowerCase();
  if (canonical && CANONICAL_TO_SERVICE_LABEL[canonical]) {
    return CANONICAL_TO_SERVICE_LABEL[canonical];
  }

  const fromArm = resourceLabelForRow(row);
  if (fromArm) return fromArm;

  const props = row.properties || {};
  const armType = props.armResourceType || props.arm_resource_type || row.armResourceType;
  if (armType && String(armType).includes('/')) {
    return String(armType).split('/').pop().replace(/_/g, ' ');
  }
  return '';
}

export function resourceLabelForFinding(finding, resource) {
  return resourceLabelForRow(resource)
    || resourceLabelForRow({
      id: finding?.resource_id,
      type: finding?.resource_type,
    })
    || '';
}
