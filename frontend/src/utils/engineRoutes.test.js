import { engineComponentSectionId, engineRulesUrl } from './engineRoutes';

describe('engineRoutes', () => {
  it('builds component-focused engine URL', () => {
    expect(engineRulesUrl('Virtual Machines')).toBe('/engine?component=Virtual%20Machines');
    expect(engineRulesUrl()).toBe('/engine');
  });

  it('builds stable section ids', () => {
    expect(engineComponentSectionId('Virtual Machines')).toBe('engine-component-virtual-machines');
    expect(engineComponentSectionId('App Service')).toBe('engine-component-app-service');
  });
});
