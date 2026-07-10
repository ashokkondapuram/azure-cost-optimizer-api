/**
 * Azure Architecture icons via react-az-icons (ISC).
 * Single source of truth for page, route, API path, ARM, and canonical resource-type icons.
 */
import AzVirtualMachine from 'react-az-icons/dist/components/AzVirtualMachine';
import AzVMScaleSets from 'react-az-icons/dist/components/AzVMScaleSets';
import AzDisks from 'react-az-icons/dist/components/AzDisks';
import AzDisksSnapshots from 'react-az-icons/dist/components/AzDisksSnapshots';
import AzBatchAccounts from 'react-az-icons/dist/components/AzBatchAccounts';
import AzVirtualDesktop from 'react-az-icons/dist/components/AzVirtualDesktop';
import AzKubernetesServices from 'react-az-icons/dist/components/AzKubernetesServices';
import AzContainerRegistries from 'react-az-icons/dist/components/AzContainerRegistries';
import AzContainerInstances from 'react-az-icons/dist/components/AzContainerInstances';
import AzAppServices from 'react-az-icons/dist/components/AzAppServices';
import AzServerFarm from 'react-az-icons/dist/components/AzServerFarm';
import AzStaticApps from 'react-az-icons/dist/components/AzStaticApps';
import AzStorageAccounts from 'react-az-icons/dist/components/AzStorageAccounts';
import AzPublicIPAddresses from 'react-az-icons/dist/components/AzPublicIPAddresses';
import AzVirtualNetworks from 'react-az-icons/dist/components/AzVirtualNetworks';
import AzNetworkInterfaces from 'react-az-icons/dist/components/AzNetworkInterfaces';
import AzPrivateEndpoints from 'react-az-icons/dist/components/AzPrivateEndpoints';
import AzPrivateLinkServices from 'react-az-icons/dist/components/AzPrivateLinkServices';
import AzLoadBalancers from 'react-az-icons/dist/components/AzLoadBalancers';
import AzApplicationGateways from 'react-az-icons/dist/components/AzApplicationGateways';
import AzNetworkSecurityGroup from 'react-az-icons/dist/components/AzNetworkSecurityGroup';
import AzNAT from 'react-az-icons/dist/components/AzNAT';
import AzDNS from 'react-az-icons/dist/components/AzDNS';
import AzFrontDoorandCDNProfiles from 'react-az-icons/dist/components/AzFrontDoorandCDNProfiles';
import AzCDNProfiles from 'react-az-icons/dist/components/AzCDNProfiles';
import AzFirewalls from 'react-az-icons/dist/components/AzFirewalls';
import AzExpressRouteCircuits from 'react-az-icons/dist/components/AzExpressRouteCircuits';
import AzVPNGateway from 'react-az-icons/dist/components/AzVPNGateway';
import AzSQLServer from 'react-az-icons/dist/components/AzSQLServer';
import AzCosmosDB from 'react-az-icons/dist/components/AzCosmosDB';
import AzDatabasePostgreSQLServer from 'react-az-icons/dist/components/AzDatabasePostgreSQLServer';
import AzDatabaseMySQLServer from 'react-az-icons/dist/components/AzDatabaseMySQLServer';
import AzCacheRedis from 'react-az-icons/dist/components/AzCacheRedis';
import AzKeyVaults from 'react-az-icons/dist/components/AzKeyVaults';
import AzLogAnalyticsWorkspaces from 'react-az-icons/dist/components/AzLogAnalyticsWorkspaces';
import AzApplicationInsights from 'react-az-icons/dist/components/AzApplicationInsights';
import AzMonitor from 'react-az-icons/dist/components/AzMonitor';
import AzLogicApps from 'react-az-icons/dist/components/AzLogicApps';
import AzDataFactories from 'react-az-icons/dist/components/AzDataFactories';
import AzAPIManagement from 'react-az-icons/dist/components/AzAPIManagement';
import AzEventHubs from 'react-az-icons/dist/components/AzEventHubs';
import AzServiceBus from 'react-az-icons/dist/components/AzServiceBus';
import AzSignalR from 'react-az-icons/dist/components/AzSignalR';
import AzDatabricks from 'react-az-icons/dist/components/AzDatabricks';
import AzSynapseAnalytics from 'react-az-icons/dist/components/AzSynapseAnalytics';
import AzDataExplorerClusters from 'react-az-icons/dist/components/AzDataExplorerClusters';
import AzHDInsightClusters from 'react-az-icons/dist/components/AzHDInsightClusters';
import AzMachineLearningWorkspacescolor from 'react-az-icons/dist/components/AzMachineLearningWorkspacescolor';
import AzPowerBIEmbedded from 'react-az-icons/dist/components/AzPowerBIEmbedded';
import AzRecoveryServicesVaults from 'react-az-icons/dist/components/AzRecoveryServicesVaults';
import AzAutomationAccounts from 'react-az-icons/dist/components/AzAutomationAccounts';
import AzCognitiveSearch from 'react-az-icons/dist/components/AzCognitiveSearch';
import AzCostManagement from 'react-az-icons/dist/components/AzCostManagement';
import AzCostManagementandBilling from 'react-az-icons/dist/components/AzCostManagementandBilling';
import AzCostAnalysis from 'react-az-icons/dist/components/AzCostAnalysis';
import AzCostBudgets from 'react-az-icons/dist/components/AzCostBudgets';
import AzSubscriptions from 'react-az-icons/dist/components/AzSubscriptions';
import AzResourceGroups from 'react-az-icons/dist/components/AzResourceGroups';
import AzResourceGroupList from 'react-az-icons/dist/components/AzResourceGroupList';
import AzDashboard from 'react-az-icons/dist/components/AzDashboard';
import AzManagementPortal from 'react-az-icons/dist/components/AzManagementPortal';
import AzActivityLog from 'react-az-icons/dist/components/AzActivityLog';
import AzMonitorDashboard from 'react-az-icons/dist/components/AzMonitorDashboard';
import AzCognativeServicesRecommendations from 'react-az-icons/dist/components/AzCognativeServicesRecommendations';
import AzServiceHealth from 'react-az-icons/dist/components/AzServiceHealth';
import AzUpdates from 'react-az-icons/dist/components/AzUpdates';

/** Logical key → Azure icon component */
export const ICON_COMPONENTS = {
  virtualMachine: AzVirtualMachine,
  vmScaleSets: AzVMScaleSets,
  vmFleet: AzVMScaleSets,
  disks: AzDisks,
  diskSnapshot: AzDisksSnapshots,
  batch: AzBatchAccounts,
  virtualDesktop: AzVirtualDesktop,
  kubernetes: AzKubernetesServices,
  aks: AzKubernetesServices,
  nodepool: AzVMScaleSets,
  k8sPod: AzContainerInstances,
  k8sNode: AzVirtualMachine,
  k8sNs: AzResourceGroupList,
  containerRegistry: AzContainerRegistries,
  containerInstance: AzContainerInstances,
  container: AzContainerRegistries,
  appService: AzAppServices,
  serverFarm: AzServerFarm,
  staticWeb: AzStaticApps,
  storage: AzStorageAccounts,
  publicIp: AzPublicIPAddresses,
  virtualNetwork: AzVirtualNetworks,
  networkInterface: AzNetworkInterfaces,
  loadBalancer: AzLoadBalancers,
  appGateway: AzApplicationGateways,
  nsg: AzNetworkSecurityGroup,
  nat: AzNAT,
  dns: AzDNS,
  privateEndpoint: AzPrivateEndpoints,
  privateLinkService: AzPrivateLinkServices,
  frontDoor: AzFrontDoorandCDNProfiles,
  cdn: AzCDNProfiles,
  firewall: AzFirewalls,
  expressRoute: AzExpressRouteCircuits,
  vpnGateway: AzVPNGateway,
  sql: AzSQLServer,
  cosmosdb: AzCosmosDB,
  postgresql: AzDatabasePostgreSQLServer,
  mysql: AzDatabaseMySQLServer,
  redis: AzCacheRedis,
  keyVault: AzKeyVaults,
  logAnalytics: AzLogAnalyticsWorkspaces,
  appInsights: AzApplicationInsights,
  monitor: AzMonitor,
  logicApps: AzLogicApps,
  dataFactory: AzDataFactories,
  apiManagement: AzAPIManagement,
  eventHubs: AzEventHubs,
  serviceBus: AzServiceBus,
  signalR: AzSignalR,
  databricks: AzDatabricks,
  synapse: AzSynapseAnalytics,
  dataExplorer: AzDataExplorerClusters,
  hdInsight: AzHDInsightClusters,
  machineLearning: AzMachineLearningWorkspacescolor,
  powerBi: AzPowerBIEmbedded,
  recoveryVault: AzRecoveryServicesVaults,
  automation: AzAutomationAccounts,
  cognitiveSearch: AzCognitiveSearch,
  costManagement: AzCostManagement,
  costBilling: AzCostManagementandBilling,
  costAnalysis: AzCostAnalysis,
  costBudgets: AzCostBudgets,
  subscription: AzSubscriptions,
  resourceGroup: AzResourceGroups,
  dashboard: AzDashboard,
  portal: AzManagementPortal,
  findings: AzCostAnalysis,
  recommendations: AzCognativeServicesRecommendations,
  history: AzActivityLog,
  serviceHealth: AzServiceHealth,
  updates: AzUpdates,
  engine: AzMonitorDashboard,
  optimization: AzMonitorDashboard,
  default: AzManagementPortal,
};

/** Canonical resource_snapshots.resource_type → logical key (mirrors app/resource_type_map.py) */
export const CANONICAL_TYPE_KEYS = {
  'compute/vm': 'virtualMachine',
  'compute/vmss': 'vmScaleSets',
  'compute/disk': 'disks',
  'compute/snapshot': 'diskSnapshot',
  'compute/batch': 'batch',
  'compute/avd': 'virtualDesktop',
  'containers/aks': 'aks',
  'containers/acr': 'containerRegistry',
  'containers/aci': 'containerInstance',
  'storage/account': 'storage',
  'network/publicip': 'publicIp',
  'network/vnet': 'virtualNetwork',
  'network/nic': 'networkInterface',
  'network/nat': 'nat',
  'network/loadbalancer': 'loadBalancer',
  'network/appgateway': 'appGateway',
  'network/nsg': 'nsg',
  'network/privateendpoint': 'privateEndpoint',
  'network/privatelinkservice': 'privateLinkService',
  'network/privatedns': 'dns',
  'network/dns': 'dns',
  'network/frontdoor': 'frontDoor',
  'network/firewall': 'firewall',
  'network/expressroute': 'expressRoute',
  'network/vpngateway': 'vpnGateway',
  'network/cdn': 'cdn',
  'database/sql': 'sql',
  'database/cosmosdb': 'cosmosdb',
  'database/postgresql': 'postgresql',
  'database/redis': 'redis',
  'database/mysql': 'mysql',
  'appservice/webapp': 'appService',
  'appservice/plan': 'serverFarm',
  'appservice/staticweb': 'staticWeb',
  'security/keyvault': 'keyVault',
  'monitoring/loganalytics': 'logAnalytics',
  'monitoring/appinsights': 'appInsights',
  'monitoring/alerts': 'monitor',
  'integration/logicapp': 'logicApps',
  'integration/datafactory': 'dataFactory',
  'integration/apim': 'apiManagement',
  'messaging/eventhub': 'eventHubs',
  'messaging/servicebus': 'serviceBus',
  'messaging/signalr': 'signalR',
  'analytics/databricks': 'databricks',
  'analytics/synapse': 'synapse',
  'analytics/adx': 'dataExplorer',
  'analytics/hdinsight': 'hdInsight',
  'analytics/mlworkspace': 'machineLearning',
  'analytics/powerbi': 'powerBi',
  'backup/recoveryvault': 'recoveryVault',
  'automation/automation': 'automation',
  'search/cognitivesearch': 'cognitiveSearch',
};

/** Prefix fallback when subtype is not listed explicitly */
export const CANONICAL_PREFIX_KEYS = {
  'compute/': 'virtualMachine',
  'containers/': 'aks',
  'storage/': 'storage',
  'network/': 'publicIp',
  'database/': 'sql',
  'appservice/': 'appService',
  'security/': 'keyVault',
  'monitoring/': 'monitor',
  'integration/': 'apiManagement',
  'messaging/': 'eventHubs',
  'analytics/': 'databricks',
  'backup/': 'recoveryVault',
  'automation/': 'automation',
  'search/': 'cognitiveSearch',
};

/** ARM resource type (any casing) → logical key */
export const ARM_TYPE_KEYS = {
  'microsoft.compute/virtualmachines': 'virtualMachine',
  'microsoft.compute/virtualmachinescalesets': 'vmScaleSets',
  'microsoft.compute/disks': 'disks',
  'microsoft.compute/snapshots': 'diskSnapshot',
  'microsoft.batch/batchaccounts': 'batch',
  'microsoft.desktopvirtualization/hostpools': 'virtualDesktop',
  'microsoft.desktopvirtualization/workspaces': 'virtualDesktop',
  'microsoft.containerservice/managedclusters': 'aks',
  'microsoft.containerregistry/registries': 'containerRegistry',
  'microsoft.containerinstance/containergroups': 'containerInstance',
  'microsoft.storage/storageaccounts': 'storage',
  'microsoft.web/sites': 'appService',
  'microsoft.web/serverfarms': 'serverFarm',
  'microsoft.web/staticsites': 'staticWeb',
  'microsoft.sql/servers': 'sql',
  'microsoft.sql/databases': 'sql',
  'microsoft.dbforpostgresql/flexibleservers': 'postgresql',
  'microsoft.dbforpostgresql/servers': 'postgresql',
  'microsoft.dbformysql/flexibleservers': 'mysql',
  'microsoft.dbformysql/servers': 'mysql',
  'microsoft.documentdb/databaseaccounts': 'cosmosdb',
  'microsoft.cache/redis': 'redis',
  'microsoft.keyvault/vaults': 'keyVault',
  'microsoft.network/publicipaddresses': 'publicIp',
  'microsoft.network/virtualnetworks': 'virtualNetwork',
  'microsoft.network/networkinterfaces': 'networkInterface',
  'microsoft.network/loadbalancers': 'loadBalancer',
  'microsoft.network/applicationgateways': 'appGateway',
  'microsoft.network/networksecuritygroups': 'nsg',
  'microsoft.network/natgateways': 'nat',
  'microsoft.network/privateendpoints': 'privateEndpoint',
  'microsoft.network/privatelinkservices': 'privateLinkService',
  'microsoft.network/privatednszones': 'dns',
  'microsoft.network/dnszones': 'dns',
  'microsoft.network/frontdoors': 'frontDoor',
  'microsoft.network/azurefirewalls': 'firewall',
  'microsoft.network/firewallpolicies': 'firewall',
  'microsoft.network/expressroutecircuits': 'expressRoute',
  'microsoft.network/vpngateways': 'vpnGateway',
  'microsoft.cdn/profiles': 'cdn',
  'microsoft.operationalinsights/workspaces': 'logAnalytics',
  'microsoft.insights/components': 'appInsights',
  'microsoft.insights/metricalerts': 'monitor',
  'microsoft.alertsmanagement/smartdetectoralertrules': 'monitor',
  'microsoft.logic/workflows': 'logicApps',
  'microsoft.datafactory/factories': 'dataFactory',
  'microsoft.apimanagement/service': 'apiManagement',
  'microsoft.eventhub/namespaces': 'eventHubs',
  'microsoft.servicebus/namespaces': 'serviceBus',
  'microsoft.signalrservice/webpubsub': 'signalR',
  'microsoft.databricks/workspaces': 'databricks',
  'microsoft.synapse/workspaces': 'synapse',
  'microsoft.kusto/clusters': 'dataExplorer',
  'microsoft.hdinsight/clusters': 'hdInsight',
  'microsoft.machinelearningservices/workspaces': 'machineLearning',
  'microsoft.powerbidedicated/capacities': 'powerBi',
  'microsoft.recoveryservices/vaults': 'recoveryVault',
  'microsoft.automation/automationaccounts': 'automation',
  'microsoft.search/searchservices': 'cognitiveSearch',
  'microsoft.costmanagement/exports': 'costManagement',
};

/** FOCUS / display service name (lowercase) → logical key */
export const SERVICE_NAME_KEYS = {
  'virtual machines': 'virtualMachine',
  'virtual machine scale sets': 'vmScaleSets',
  'storage': 'storage',
  'kubernetes service': 'aks',
  'container registry': 'containerRegistry',
  'container instances': 'containerInstance',
  'sql database': 'sql',
  'azure cosmos db': 'cosmosdb',
  'azure database for postgresql': 'postgresql',
  'azure database for mysql': 'mysql',
  'azure cache for redis': 'redis',
  'app service': 'appService',
  'azure app service': 'appService',
  'static web apps': 'staticWeb',
  'key vault': 'keyVault',
  'virtual network': 'virtualNetwork',
  'virtual networks': 'virtualNetwork',
  'load balancer': 'loadBalancer',
  'application gateway': 'appGateway',
  'virtual network peering': 'virtualNetwork',
  'bandwidth': 'publicIp',
  'ip addresses': 'publicIp',
  'azure firewall': 'firewall',
  'azure front door': 'frontDoor',
  'content delivery network': 'cdn',
  'azure private link': 'privateEndpoint',
  'private link': 'privateEndpoint',
  'nat gateway': 'nat',
  'azure nat gateway': 'nat',
  'vpn gateway': 'vpnGateway',
  'virtual wan': 'virtualNetwork',
  'network watcher': 'monitor',
  'log analytics': 'logAnalytics',
  'microsoft.insights': 'appInsights',
  'application insights': 'appInsights',
  'azure monitor': 'monitor',
  'logic apps': 'logicApps',
  'azure data factory': 'dataFactory',
  'data factory': 'dataFactory',
  'api management': 'apiManagement',
  'event hubs': 'eventHubs',
  'service bus': 'serviceBus',
  'azure databricks': 'databricks',
  'azure synapse analytics': 'synapse',
  'azure data explorer': 'dataExplorer',
  'azure hdinsight': 'hdInsight',
  'azure machine learning': 'machineLearning',
  'power bi embedded': 'powerBi',
  'backup': 'recoveryVault',
  'recovery services': 'recoveryVault',
  'automation': 'automation',
  'azure cognitive search': 'cognitiveSearch',
  'search': 'cognitiveSearch',
};

export const CATEGORY_KEYS = {
  COMPUTE: 'virtualMachine',
  KUBERNETES: 'aks',
  STORAGE: 'storage',
  NETWORK: 'virtualNetwork',
  DATABASE: 'sql',
  SECURITY: 'keyVault',
  COST: 'costManagement',
  GOVERNANCE: 'costBudgets',
  MONITORING: 'monitor',
};

export const NAV_GROUP_KEYS = {
  compute: 'virtualMachine',
  containers: 'aks',
  appservices: 'appService',
  storage: 'storage',
  networking: 'virtualNetwork',
  databases: 'sql',
  monitoring: 'monitor',
  integration: 'apiManagement',
  messaging: 'eventHubs',
  analytics: 'databricks',
  backup: 'recoveryVault',
  search: 'cognitiveSearch',
  security: 'keyVault',
  optimization: 'optimization',
  settings: 'portal',
  insights: 'costAnalysis',
  savings: 'costBudgets',
  governance: 'keyVault',
  operations: 'automation',
};

export const PAGE_ICON_KEYS = {
  dashboard: 'dashboard',
  costs: 'costManagement',
  findings: 'findings',
  recommendations: 'recommendations',
  actions: 'recommendations',
  scoreboard: 'engine',
  optimizationHub: 'recommendations',
  wasteHeatmap: 'costAnalysis',
  anomalyDetector: 'monitor',
  demandForecaster: 'machineLearning',
  savingsPlanner: 'costBudgets',
  reservationAdvisor: 'recommendations',
  budgetsNav: 'costBudgets',
  tagCompliance: 'resourceGroup',
  policyEnforcement: 'keyVault',
  governanceDashboard: 'monitor',
  plannedMaintenance: 'updates',
  quotaUsage: 'subscription',
  autoScheduler: 'automation',
  notificationsNav: 'signalR',
  optimizationTimeline: 'history',
  costAllocation: 'costBilling',
  exportCenter: 'dataFactory',
  rollout: 'optimization',
  engine: 'engine',
  history: 'history',
  optimization: 'optimization',
  apiExplorer: 'apiManagement',
  subscription: 'subscription',
  resourceGroup: 'resourceGroup',
  vms: 'virtualMachine',
  vmFleet: 'vmFleet',
  vmss: 'vmScaleSets',
  disks: 'disks',
  snapshots: 'diskSnapshot',
  aks: 'aks',
  acr: 'containerRegistry',
  aci: 'containerInstance',
  appservices: 'appService',
  appserviceplans: 'serverFarm',
  storage: 'storage',
  publicips: 'publicIp',
  vnets: 'virtualNetwork',
  nics: 'networkInterface',
  natgateways: 'nat',
  loadbalancers: 'loadBalancer',
  appgateways: 'appGateway',
  nsgs: 'nsg',
  privateendpoints: 'privateEndpoint',
  privatelinkservices: 'privateLinkService',
  privatedns: 'dns',
  sql: 'sql',
  cosmosdb: 'cosmosdb',
  postgresql: 'postgresql',
  mysql: 'mysql',
  redis: 'redis',
  keyvaults: 'keyVault',
  loganalytics: 'logAnalytics',
  appinsights: 'appInsights',
  apim: 'apiManagement',
  datafactory: 'dataFactory',
  logicapps: 'logicApps',
  eventhubs: 'eventHubs',
  servicebus: 'serviceBus',
  databricks: 'databricks',
  synapse: 'synapse',
  adx: 'dataExplorer',
  mlworkspace: 'machineLearning',
  recoveryvault: 'recoveryVault',
  cognitivesearch: 'cognitiveSearch',
  monitoring: 'monitor',
  integration: 'apiManagement',
  messaging: 'eventHubs',
  analytics: 'databricks',
  backup: 'recoveryVault',
  search: 'cognitiveSearch',
  costResources: 'costBilling',
  kubernetes: 'kubernetes',
  nodepool: 'nodepool',
  k8sPod: 'k8sPod',
  k8sNode: 'k8sNode',
  k8sNs: 'k8sNs',
  logo: 'costBilling',
  settings: 'portal',
};

export const ROUTE_ICON_KEYS = {
  '/': 'dashboard',
  '/costs': 'costManagement',
  '/cost-resources': 'costBilling',
  '/recommendations': 'recommendations',
  '/optimization-hub': 'recommendations',
  '/optimize/actions': 'recommendations',
  '/optimize/scoreboard': 'engine',
  '/engine': 'engine',
  '/admin/optimization': 'optimization',
  '/k8s': 'kubernetes',
  '/history': 'history',
  '/settings': 'portal',
  '/admin/api-explorer': 'apiManagement',
  '/vms': 'virtualMachine',
  '/vmss': 'vmScaleSets',
  '/disks': 'disks',
  '/snapshots': 'diskSnapshot',
  '/aks': 'aks',
  '/acr': 'containerRegistry',
  '/appservices': 'appService',
  '/appserviceplans': 'serverFarm',
  '/storage': 'storage',
  '/publicips': 'publicIp',
  '/vnets': 'virtualNetwork',
  '/nics': 'networkInterface',
  '/natgateways': 'nat',
  '/loadbalancers': 'loadBalancer',
  '/appgateways': 'appGateway',
  '/nsgs': 'nsg',
  '/privateendpoints': 'privateEndpoint',
  '/privatelinkservices': 'privateLinkService',
  '/privatedns': 'dns',
  '/sql': 'sql',
  '/cosmosdb': 'cosmosdb',
  '/postgresql': 'postgresql',
  '/redis': 'redis',
  '/keyvaults': 'keyVault',
  '/loganalytics': 'logAnalytics',
  '/appinsights': 'appInsights',
  '/apim': 'apiManagement',
  '/datafactory': 'dataFactory',
  '/logicapps': 'logicApps',
  '/eventhubs': 'eventHubs',
  '/servicebus': 'serviceBus',
  '/databricks': 'databricks',
  '/synapse': 'synapse',
  '/adx': 'dataExplorer',
  '/mlworkspace': 'machineLearning',
  '/recoveryvault': 'recoveryVault',
  '/cognitivesearch': 'cognitiveSearch',
  '/monitoring': 'monitor',
  '/integration': 'apiManagement',
  '/messaging': 'eventHubs',
  '/analytics': 'databricks',
  '/backup': 'recoveryVault',
  '/search': 'cognitiveSearch',
  // ── Advanced tools ─────────────────────────────────────────────────────────
  '/waste-heatmap': 'costAnalysis',
  '/tag-compliance': 'resourceGroup',
  '/planned-maintenance': 'updates',
  '/quota-usage': 'subscription',
  '/auto-scheduler': 'automation',
  '/notifications': 'signalR',
  '/anomaly-detector': 'monitor',
  '/timeline': 'history',
  '/budgets': 'costBudgets',
  '/savings-planner': 'costBudgets',
  '/policy': 'keyVault',
  '/reservation-advisor': 'recommendations',
  '/governance': 'monitor',
  '/cost-allocation': 'costBilling',
  '/export-center': 'dataFactory',
  '/demand-forecaster': 'machineLearning',
};

export const API_PATH_KEYS = {
  '/resources/from-cost': 'costBilling',
  '/resources/vms': 'virtualMachine',
  '/resources/vmss': 'vmScaleSets',
  '/resources/disks': 'disks',
  '/resources/snapshots': 'diskSnapshot',
  '/resources/aks': 'aks',
  '/resources/acr': 'containerRegistry',
  '/resources/appservices': 'appService',
  '/resources/appserviceplans': 'serverFarm',
  '/resources/storage': 'storage',
  '/resources/publicips': 'publicIp',
  '/resources/vnets': 'virtualNetwork',
  '/resources/nics': 'networkInterface',
  '/resources/natgateways': 'nat',
  '/resources/loadbalancers': 'loadBalancer',
  '/resources/appgateways': 'appGateway',
  '/resources/nsgs': 'nsg',
  '/resources/privateendpoints': 'privateEndpoint',
  '/resources/privatelinkservices': 'privateLinkService',
  '/resources/privatedns': 'dns',
  '/resources/sql': 'sql',
  '/resources/cosmosdb': 'cosmosdb',
  '/resources/postgresql': 'postgresql',
  '/resources/mysql': 'mysql',
  '/resources/redis': 'redis',
  '/resources/keyvaults': 'keyVault',
  '/resources/loganalytics': 'logAnalytics',
  '/resources/appinsights': 'appInsights',
  '/resources/apim': 'apiManagement',
  '/resources/datafactory': 'dataFactory',
  '/resources/logicapps': 'logicApps',
  '/resources/eventhubs': 'eventHubs',
  '/resources/servicebus': 'serviceBus',
  '/resources/databricks': 'databricks',
  '/resources/synapse': 'synapse',
  '/resources/adx': 'dataExplorer',
  '/resources/mlworkspace': 'machineLearning',
  '/resources/recoveryvault': 'recoveryVault',
  '/resources/cognitivesearch': 'cognitiveSearch',
  '/resources/monitoring': 'monitor',
  '/resources/integration': 'apiManagement',
  '/resources/messaging': 'eventHubs',
  '/resources/analytics': 'databricks',
  '/resources/backup': 'recoveryVault',
  '/resources/search': 'cognitiveSearch',
};

const COMPONENT_NAME_KEYS = {
  'Virtual Machines': 'virtualMachine',
  'Managed Disks': 'disks',
  'Disk Snapshots': 'diskSnapshot',
  'App Service': 'appService',
  'App Service Plans': 'serverFarm',
  AKS: 'aks',
  'Storage Accounts': 'storage',
  'Public IPs': 'publicIp',
  'Virtual Networks': 'virtualNetwork',
  'Load Balancers': 'loadBalancer',
  'Application Gateways': 'appGateway',
  'Network Security Groups': 'nsg',
  'NAT Gateways': 'nat',
  'Network Interfaces': 'networkInterface',
  SQL: 'sql',
  'SQL Database': 'sql',
  'SQL Servers': 'sql',
  'Cosmos DB': 'cosmosdb',
  PostgreSQL: 'postgresql',
  Redis: 'redis',
  'Redis Cache': 'redis',
  'Key Vault': 'keyVault',
  'Key Vaults': 'keyVault',
  'Container Registry': 'containerRegistry',
  'Container Registries': 'containerRegistry',
  Monitoring: 'monitor',
  Integration: 'apiManagement',
  Messaging: 'eventHubs',
  Analytics: 'databricks',
  Backup: 'recoveryVault',
  Search: 'cognitiveSearch',
  Networking: 'frontDoor',
  'Cost export': 'costBilling',
  Budgets: 'costBudgets',
  Commitments: 'costBilling',
  Governance: 'costBudgets',
};

/** Legacy /icons/*.svg path → logical key */
const LEGACY_SRC_KEYS = {
  '/icons/azure/virtual-machine.svg': 'virtualMachine',
  '/icons/azure/virtual-machine-scale-set.svg': 'vmScaleSets',
  '/icons/azure/all-virtual-machines.svg': 'vmFleet',
  '/icons/azure/storage-cache.svg': 'storage',
  '/icons/azure/managed-clusters.svg': 'aks',
  '/icons/azure/container-group.svg': 'appService',
  '/icons/azure/global-view.svg': 'publicIp',
  '/icons/azure/cost-management.svg': 'costManagement',
  '/icons/azure/subscription.svg': 'subscription',
  '/icons/azure/resource-groups.svg': 'resourceGroup',
  '/icons/aks.svg': 'aks',
  '/icons/kubernetes.svg': 'kubernetes',
  '/icons/nodepool.svg': 'nodepool',
  '/icons/k8s-pod.svg': 'k8sPod',
  '/icons/k8s-node.svg': 'k8sNode',
  '/icons/k8s-ns.svg': 'k8sNs',
  '/icons/container.svg': 'containerRegistry',
  '/icons/virtual-machine.svg': 'virtualMachine',
};

function normalizeArmType(type) {
  return (type || '').trim().toLowerCase();
}

function otherSlugToArmProvider(slug) {
  if (!slug) return '';
  const idx = slug.indexOf('-');
  if (idx < 0) return slug;
  return `${slug.slice(0, idx)}/${slug.slice(idx + 1)}`;
}

export function iconKeyForCanonicalType(type) {
  if (!type) return null;
  const canonical = (type || '').trim().toLowerCase();
  if (CANONICAL_TYPE_KEYS[canonical]) return CANONICAL_TYPE_KEYS[canonical];
  for (const [prefix, key] of Object.entries(CANONICAL_PREFIX_KEYS)) {
    if (canonical.startsWith(prefix)) return key;
  }
  if (canonical.startsWith('other/')) {
    const arm = otherSlugToArmProvider(canonical.slice(6));
    return iconKeyForAzureType(arm) || null;
  }
  return null;
}

export function iconKeyForServiceName(serviceName) {
  const svc = (serviceName || '').trim().toLowerCase();
  if (!svc) return null;
  if (SERVICE_NAME_KEYS[svc]) return SERVICE_NAME_KEYS[svc];
  for (const [needle, key] of Object.entries(SERVICE_NAME_KEYS)) {
    if (svc.includes(needle)) return key;
  }
  return null;
}

export function getIconComponent(key) {
  if (!key) return ICON_COMPONENTS.default;
  return ICON_COMPONENTS[key] || ICON_COMPONENTS.default;
}

export function legacySrcToKey(src) {
  return LEGACY_SRC_KEYS[src] || null;
}

export function iconKeyForAzureType(type) {
  if (!type) return null;

  const canonical = iconKeyForCanonicalType(type);
  if (canonical) return canonical;

  const normalized = normalizeArmType(type);
  if (ARM_TYPE_KEYS[normalized]) return ARM_TYPE_KEYS[normalized];

  const pascal = type.includes('/') ? type : null;
  if (pascal && ARM_TYPE_KEYS[normalizeArmType(pascal)]) {
    return ARM_TYPE_KEYS[normalizeArmType(pascal)];
  }

  const t = type;
  if (t.includes('virtualMachines')) return 'virtualMachine';
  if (t.includes('virtualMachineScaleSets')) return 'vmScaleSets';
  if (t.includes('managedClusters') || t.includes('ContainerService')) return 'aks';
  if (t.includes('ContainerRegistry')) return 'containerRegistry';
  if (t.includes('ContainerInstance')) return 'containerInstance';
  if (t.includes('operationalinsights') || t.includes('OperationalInsights')) return 'logAnalytics';
  if (t.includes('insights/components') || t.includes('ApplicationInsights')) return 'appInsights';
  if (t.includes('datafactory') || t.includes('DataFactory')) return 'dataFactory';
  if (t.includes('apimanagement') || t.includes('ApiManagement')) return 'apiManagement';
  if (t.includes('logic/workflows') || t.includes('Logic')) return 'logicApps';
  if (t.includes('eventhub') || t.includes('EventHub')) return 'eventHubs';
  if (t.includes('servicebus') || t.includes('ServiceBus')) return 'serviceBus';
  if (t.includes('databricks') || t.includes('Databricks')) return 'databricks';
  if (t.includes('synapse') || t.includes('Synapse')) return 'synapse';
  if (t.includes('kusto') || t.includes('Kusto')) return 'dataExplorer';
  if (t.includes('machinelearning') || t.includes('MachineLearning')) return 'machineLearning';
  if (t.includes('recoveryservices') || t.includes('RecoveryServices')) return 'recoveryVault';
  if (t.includes('search/search') || t.includes('Search')) return 'cognitiveSearch';
  if (t.includes('Storage')) return 'storage';
  if (t.includes('publicIP')) return 'publicIp';
  if (t.includes('networkInterfaces')) return 'networkInterface';
  if (t.includes('loadBalancers')) return 'loadBalancer';
  if (t.includes('applicationGateways')) return 'appGateway';
  if (t.includes('networkSecurityGroups')) return 'nsg';
  if (t.includes('natGateways')) return 'nat';
  if (t.includes('azurefirewalls') || t.includes('Firewall')) return 'firewall';
  if (t.includes('frontdoors') || t.includes('FrontDoor')) return 'frontDoor';
  if (t.includes('cdn')) return 'cdn';
  if (t.includes('Network')) return 'publicIp';
  if (t.includes('PostgreSQL')) return 'postgresql';
  if (t.includes('MySQL')) return 'mysql';
  if (t.includes('DocumentDB') || t.includes('Cosmos')) return 'cosmosdb';
  if (t.includes('Sql')) return 'sql';
  if (t.includes('redis') || t.includes('Redis')) return 'redis';
  if (t.includes('KeyVault')) return 'keyVault';
  if (t.includes('Web/sites') || t.includes('Web')) return 'appService';
  if (t.includes('CostManagement')) return 'costManagement';
  return null;
}

export function iconKeyForCategory(category) {
  return CATEGORY_KEYS[(category || '').toUpperCase()] || null;
}

export function iconKeyForComponent(component) {
  if (!component) return null;
  if (COMPONENT_NAME_KEYS[component]) return COMPONENT_NAME_KEYS[component];
  const lower = component.toLowerCase();
  if (lower.includes('log analytics')) return 'logAnalytics';
  if (lower.includes('application insights') || lower.includes('app insights')) return 'appInsights';
  if (lower.includes('api management')) return 'apiManagement';
  if (lower.includes('data factory')) return 'dataFactory';
  if (lower.includes('logic app')) return 'logicApps';
  if (lower.includes('event hub')) return 'eventHubs';
  if (lower.includes('service bus')) return 'serviceBus';
  if (lower.includes('databricks')) return 'databricks';
  if (lower.includes('synapse')) return 'synapse';
  if (lower.includes('data explorer') || lower.includes('adx')) return 'dataExplorer';
  if (lower.includes('machine learning')) return 'machineLearning';
  if (lower.includes('backup') || lower.includes('recovery')) return 'recoveryVault';
  if (lower.includes('cognitive search') || lower.includes('ai search')) return 'cognitiveSearch';
  if (lower.includes('vm') || lower.includes('virtual machine')) return 'virtualMachine';
  if (lower.includes('disk')) return 'disks';
  if (lower.includes('snapshot')) return 'diskSnapshot';
  if (lower.includes('aks') || lower.includes('kubernetes')) return 'aks';
  if (lower.includes('storage')) return 'storage';
  if (lower.includes('firewall')) return 'firewall';
  if (lower.includes('front door') || lower.includes('cdn')) return 'frontDoor';
  if (lower.includes('gateway')) return 'appGateway';
  if (lower.includes('load balancer')) return 'loadBalancer';
  if (lower.includes('virtual network') || lower.includes('vnet')) return 'virtualNetwork';
  if (lower.includes('network interface') || lower.includes(' nic')) return 'networkInterface';
  if (lower.includes('public ip')) return 'publicIp';
  if (lower.includes('network') || lower.includes(' ip')) return 'virtualNetwork';
  if (lower.includes('cosmos')) return 'cosmosdb';
  if (lower.includes('postgres')) return 'postgresql';
  if (lower.includes('mysql')) return 'mysql';
  if (lower.includes('sql') || lower.includes('database')) return 'sql';
  if (lower.includes('redis')) return 'redis';
  if (lower.includes('key vault')) return 'keyVault';
  if (lower.includes('app service')) return 'appService';
  if (lower.includes('container registr')) return 'containerRegistry';
  if (lower.includes('nat')) return 'nat';
  if (lower.includes('monitor')) return 'monitor';
  if (lower.includes('cost') || lower.includes('budget')) return 'costManagement';
  return null;
}

export function iconKeyForRoute(pathname) {
  return ROUTE_ICON_KEYS[pathname] || null;
}

export function iconKeyForApiPath(apiPath) {
  return API_PATH_KEYS[apiPath] || null;
}

export function iconKeyFromResourceId(resourceId) {
  if (!resourceId) return null;
  const match = resourceId.match(/\/providers\/([^/]+\/[^/]+)/i);
  return match ? iconKeyForAzureType(match[1]) : null;
}

export function resolvePageIconKey(iconKey) {
  if (!iconKey) return null;
  return PAGE_ICON_KEYS[iconKey] || iconKey;
}

export function resolveIconKey({
  iconKey,
  src,
  armType,
  category,
  component,
  route,
  apiPath,
  resourceId,
  canonicalType,
  serviceName,
} = {}) {
  return (
    resolvePageIconKey(iconKey)
    || (src && !src.startsWith('/') ? resolvePageIconKey(src) : null)
    || legacySrcToKey(src)
    || iconKeyFromResourceId(resourceId)
    || iconKeyForAzureType(armType)
    || iconKeyForCanonicalType(canonicalType)
    || iconKeyForServiceName(serviceName)
    || iconKeyForCategory(category)
    || iconKeyForComponent(component)
    || (route != null ? iconKeyForRoute(route) : null)
    || iconKeyForApiPath(apiPath)
    || null
  );
}

/** Validate registry integrity (used in tests and dev). */
export function validateIconRegistry() {
  const errors = [];
  const checkKeys = (map, label) => {
    Object.entries(map).forEach(([k, v]) => {
      if (!ICON_COMPONENTS[v]) errors.push(`${label}: unknown icon key "${v}" for "${k}"`);
    });
  };
  checkKeys(CANONICAL_TYPE_KEYS, 'CANONICAL_TYPE_KEYS');
  checkKeys(CANONICAL_PREFIX_KEYS, 'CANONICAL_PREFIX_KEYS');
  checkKeys(ARM_TYPE_KEYS, 'ARM_TYPE_KEYS');
  checkKeys(SERVICE_NAME_KEYS, 'SERVICE_NAME_KEYS');
  checkKeys(PAGE_ICON_KEYS, 'PAGE_ICON_KEYS');
  checkKeys(ROUTE_ICON_KEYS, 'ROUTE_ICON_KEYS');
  checkKeys(API_PATH_KEYS, 'API_PATH_KEYS');
  checkKeys(NAV_GROUP_KEYS, 'NAV_GROUP_KEYS');
  checkKeys(CATEGORY_KEYS, 'CATEGORY_KEYS');
  Object.entries(COMPONENT_NAME_KEYS).forEach(([k, v]) => {
    if (!ICON_COMPONENTS[v]) errors.push(`COMPONENT_NAME_KEYS: unknown icon key "${v}" for "${k}"`);
  });
  return errors;
}
