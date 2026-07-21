/** Typed column layouts per resource list page. */

export function costColumnLabel(currency = 'CAD') {
  return `Total cost (${currency})`;
}


/** Standard list columns — details live in the insight drawer. */
export function standardResourceColumns(overrides = {}) {
  const {
    nameLabel = 'Name',
    skuLabel = 'Type / SKU',
    skuType,
    stateLabel = 'State',
    hideState = false,
  } = overrides;
  const cols = [
    { key: 'name', label: nameLabel },
    { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
    { key: 'location', label: 'Location' },
    { key: 'sku', label: skuLabel, ...(skuType ? { type: skuType } : {}) },
  ];
  if (!hideState) {
    cols.push({ key: 'state', label: stateLabel, type: 'state' });
  }
  cols.push(
    { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
    { key: 'advisor', label: 'Advisor', type: 'advisor' },
    { key: 'triggers', label: 'Cost signals', type: 'triggers' },
    { key: 'findings', label: 'Findings', type: 'findings' },
  );
  return cols;
}

export const RESOURCE_COLUMN_CONFIG = {
  '/resources/from-cost': {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'azureServiceName', label: 'Service' },
      { key: 'type', label: 'Type' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'state', label: 'Azure status', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/vmss': {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'Size / instances' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/snapshots': {
    columns: standardResourceColumns({ skuLabel: 'SKU' }),
  },
  '/resources/acr': {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'SKU' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/appservices': {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'Plan / SKU', type: 'app_service_sku' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/appserviceplans': {
    columns: standardResourceColumns({
      nameLabel: 'Plan',
      skuLabel: 'SKU / tier',
      skuType: 'app_service_plan_sku',
      stateLabel: 'Status',
    }),
  },
  '/resources/storage': {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'Replication' },
      { key: 'state', label: 'Tier' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/publicips': {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'SKU' },
      { key: 'state', label: 'Association' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/loadbalancers': {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'SKU' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/appgateways': {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'SKU / tier' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/nsgs': {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/vnets': {
    columns: standardResourceColumns({ skuLabel: 'Address space', skuType: 'vnet_address' }),
  },
  '/resources/privateendpoints': {
    columns: standardResourceColumns({ skuLabel: 'Target / status', skuType: 'pe_connection' }),
  },
  '/resources/privatelinkservices': {
    columns: standardResourceColumns({ skuLabel: 'Connections / visibility', skuType: 'pls_summary' }),
  },
  '/resources/privatedns': {
    columns: standardResourceColumns({
      nameLabel: 'Zone',
      skuLabel: 'Record sets / type',
      skuType: 'private_dns_summary',
    }),
  },
  '/resources/sql': {
    columns: [
      { key: 'name', label: 'Server' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'SKU' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/cosmosdb': {
    columns: [
      { key: 'name', label: 'Account' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'API / tier' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/postgresql': {
    columns: [
      { key: 'name', label: 'Server' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'SKU / tier' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
  '/resources/keyvaults': {
    columns: [
      { key: 'name', label: 'Vault' },
      { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
      { key: 'location', label: 'Location' },
      { key: 'sku', label: 'SKU' },
      { key: 'state', label: 'State', type: 'state' },
      { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
      { key: 'advisor', label: 'Advisor', type: 'advisor' },
      { key: 'triggers', label: 'Cost signals', type: 'triggers' },
      { key: 'findings', label: 'Findings', type: 'findings' },
    ],
  },
};

const CATEGORY_COLUMNS = [
  { key: 'name', label: 'Name' },
  { key: 'azureServiceName', label: 'Service' },
  { key: 'type', label: 'Type' },
  { key: 'resourceGroup', label: 'Resource group', alt: 'resource_group' },
  { key: 'state', label: 'Source', type: 'state' },
  { key: 'monthlyCost', label: 'Total cost', type: 'cost' },
  { key: 'advisor', label: 'Advisor', type: 'advisor' },
  { key: 'triggers', label: 'Cost signals', type: 'triggers' },
  { key: 'findings', label: 'Findings', type: 'findings' },
];

/** @deprecated Legacy aggregate API paths still supported by the backend. */
['/resources/monitoring', '/resources/integration', '/resources/messaging',
 '/resources/analytics', '/resources/backup', '/resources/search'].forEach((path) => {
  RESOURCE_COLUMN_CONFIG[path] = { columns: CATEGORY_COLUMNS };
});

const DEFAULT_RESOURCE_COLUMNS = {
  columns: standardResourceColumns(),
};

export function getColumnConfig(apiPath) {
  return RESOURCE_COLUMN_CONFIG[apiPath] || DEFAULT_RESOURCE_COLUMNS;
}
