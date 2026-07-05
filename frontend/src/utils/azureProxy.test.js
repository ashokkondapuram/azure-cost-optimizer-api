import { rewriteAzureRequestToAppProxy } from './azureProxy';

const PROXY_CONFIG = {
  managementHost: 'management.azure.com',
  routes: [
    {
      arm: '^/subscriptions$',
      proxy: '/api/azure/subscriptions',
    },
    {
      arm: '^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\\.Compute/virtualMachines$',
      proxy: '/api/azure/vms',
      query: { subscription_id: '{subscriptionId}' },
    },
  ],
};

describe('rewriteAzureRequestToAppProxy', () => {
  it('rewrites management.azure.com URLs to the app proxy', () => {
    const request = {
      url: 'https://management.azure.com/subscriptions/abc-123/providers/Microsoft.Compute/virtualMachines?api-version=2025-11-01',
      headers: {},
    };
    rewriteAzureRequestToAppProxy(request, PROXY_CONFIG);
    expect(request.url).toBe('/api/azure/vms?subscription_id=abc-123');
    expect(request.url).not.toContain('management.azure.com');
  });

  it('rewrites same-origin ARM paths to the app proxy', () => {
    const request = {
      url: '/subscriptions/abc-123/providers/Microsoft.Compute/virtualMachines?api-version=2025-11-01',
      headers: {},
    };
    rewriteAzureRequestToAppProxy(request, PROXY_CONFIG);
    expect(request.url).toBe('/api/azure/vms?subscription_id=abc-123');
  });
});
