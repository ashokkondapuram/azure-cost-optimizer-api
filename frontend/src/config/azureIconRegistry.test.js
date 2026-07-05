import {
  CANONICAL_TYPE_KEYS,
  ICON_COMPONENTS,
  PAGE_ICON_KEYS,
  ROUTE_ICON_KEYS,
  API_PATH_KEYS,
  iconKeyForCanonicalType,
  iconKeyForAzureType,
  iconKeyForServiceName,
  iconKeyForComponent,
  iconKeyFromResourceId,
  validateIconRegistry,
} from './azureIconRegistry';
import { iconForRow } from './assetIcons';

describe('azureIconRegistry', () => {
  it('has no broken icon key references', () => {
    expect(validateIconRegistry()).toEqual([]);
  });

  it('maps every canonical type to a registered component', () => {
    Object.entries(CANONICAL_TYPE_KEYS).forEach(([type, key]) => {
      expect(ICON_COMPONENTS[key]).toBeTruthy();
      expect(iconKeyForCanonicalType(type)).toBe(key);
    });
  });

  it('maps ARM resource IDs to the correct icon', () => {
    const rid = '/subscriptions/x/resourcegroups/rg/providers/Microsoft.OperationalInsights/workspaces/log-ws';
    expect(iconKeyFromResourceId(rid)).toBe('logAnalytics');
  });

  it('maps canonical row types in resource lists', () => {
    expect(iconKeyForCanonicalType('monitoring/loganalytics')).toBe('logAnalytics');
    expect(iconKeyForCanonicalType('integration/apim')).toBe('apiManagement');
    expect(iconKeyForCanonicalType('messaging/eventhub')).toBe('eventHubs');
    expect(iconKeyForCanonicalType('analytics/databricks')).toBe('databricks');
    expect(iconKeyForCanonicalType('backup/recoveryvault')).toBe('recoveryVault');
    expect(iconKeyForCanonicalType('search/cognitivesearch')).toBe('cognitiveSearch');
  });

  it('maps service names from cost export rows', () => {
    expect(iconKeyForServiceName('Log Analytics')).toBe('logAnalytics');
    expect(iconKeyForServiceName('API Management')).toBe('apiManagement');
    expect(iconKeyForServiceName('Azure Databricks')).toBe('databricks');
  });

  it('maps optimizer component labels', () => {
    expect(iconKeyForComponent('Monitoring')).toBe('monitor');
    expect(iconKeyForComponent('Integration')).toBe('apiManagement');
    expect(iconKeyForComponent('Analytics')).toBe('databricks');
    expect(iconKeyForComponent('Backup')).toBe('recoveryVault');
  });

  it('resolves row icons with canonical type before api path fallback', () => {
    const key = iconForRow(
      { type: 'monitoring/appinsights', id: '/subscriptions/x/resourcegroups/rg/providers/microsoft.insights/components/appi' },
      { apiPath: '/resources/monitoring', fallback: 'monitor' },
    );
    expect(key).toBe('appInsights');
  });

  it('defines icons for all primary routes and API paths', () => {
    [
      '/loganalytics',
      '/appinsights',
      '/apim',
      '/datafactory',
      '/logicapps',
      '/eventhubs',
      '/servicebus',
      '/databricks',
      '/synapse',
      '/adx',
      '/mlworkspace',
      '/recoveryvault',
      '/cognitivesearch',
      '/monitoring',
      '/integration',
      '/messaging',
      '/analytics',
      '/backup',
      '/search',
      '/cost-resources',
    ].forEach((route) => {
      expect(ROUTE_ICON_KEYS[route]).toBeTruthy();
      expect(ICON_COMPONENTS[ROUTE_ICON_KEYS[route]]).toBeTruthy();
    });

    [
      '/resources/loganalytics',
      '/resources/appinsights',
      '/resources/apim',
      '/resources/datafactory',
      '/resources/logicapps',
      '/resources/eventhubs',
      '/resources/servicebus',
      '/resources/databricks',
      '/resources/synapse',
      '/resources/adx',
      '/resources/mlworkspace',
      '/resources/recoveryvault',
      '/resources/cognitivesearch',
      '/resources/monitoring',
      '/resources/integration',
      '/resources/messaging',
      '/resources/analytics',
      '/resources/backup',
      '/resources/search',
      '/resources/from-cost',
    ].forEach((path) => {
      expect(API_PATH_KEYS[path]).toBeTruthy();
      expect(ICON_COMPONENTS[API_PATH_KEYS[path]]).toBeTruthy();
    });
  });

  it('defines page icon keys used by the shell', () => {
    [
      'loganalytics', 'appinsights', 'apim', 'datafactory', 'logicapps',
      'eventhubs', 'servicebus', 'databricks', 'synapse', 'adx', 'mlworkspace',
      'recoveryvault', 'cognitivesearch', 'costResources', 'optimization', 'apiExplorer',
    ].forEach((key) => {
      expect(PAGE_ICON_KEYS[key]).toBeTruthy();
      expect(ICON_COMPONENTS[PAGE_ICON_KEYS[key]]).toBeTruthy();
    });
  });

  it('normalizes ARM provider types case-insensitively', () => {
    expect(iconKeyForAzureType('Microsoft.ApiManagement/service')).toBe('apiManagement');
    expect(iconKeyForAzureType('microsoft.kusto/clusters')).toBe('dataExplorer');
  });

  it('maps virtual networks to the virtual network icon', () => {
    expect(iconKeyForCanonicalType('network/vnet')).toBe('virtualNetwork');
    expect(iconKeyForAzureType('Microsoft.Network/virtualNetworks')).toBe('virtualNetwork');
    expect(iconKeyForServiceName('Virtual Network')).toBe('virtualNetwork');
    expect(PAGE_ICON_KEYS.vnets).toBe('virtualNetwork');
    expect(ROUTE_ICON_KEYS['/vnets']).toBe('virtualNetwork');
    expect(API_PATH_KEYS['/resources/vnets']).toBe('virtualNetwork');
  });
});
