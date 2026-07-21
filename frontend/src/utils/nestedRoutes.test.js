import {
  explorerPath,
  optimizationHubPath,
  actionCentrePath,
  actionCentreProposedPath,
  actionCentreViewFromPath,
  legacyOptimizationHubRedirect,
  legacyExplorerRedirect,
  explorerTabFromPath,
  hubTabFromPath,
} from './nestedRoutes';

describe('nestedRoutes', () => {
  test('explorer paths', () => {
    expect(explorerPath()).toBe('/explorer');
    expect(explorerTabFromPath('/explorer')).toBe('inventory');
    expect(explorerTabFromPath('/explorer/inventory')).toBe('inventory');
    expect(explorerTabFromPath('/explorer/issues')).toBe('issues');
  });

  test('action centre paths', () => {
    expect(actionCentrePath('resources')).toBe('/action-centre');
    expect(actionCentrePath('workflow')).toBe('/action-centre?hasAction=1');
    expect(actionCentreProposedPath()).toBe('/action-centre?hasAction=1');
    expect(actionCentreViewFromPath('/action-centre')).toBe('resources');
    expect(actionCentreViewFromPath('/action-centre/workflow')).toBe('workflow');
  });

  test('hub paths alias proposed-actions filter', () => {
    expect(optimizationHubPath('actions')).toBe('/action-centre?hasAction=1');
    expect(hubTabFromPath('/optimization-hub')).toBe('actions');
    expect(hubTabFromPath('/action-centre/workflow')).toBe('actions');
  });

  test('legacy explorer redirects', () => {
    expect(legacyExplorerRedirect('/explorer')).toBe('/explorer');
    expect(legacyExplorerRedirect('/explorer/inventory')).toBe('/explorer');
    expect(legacyExplorerRedirect('/explorer/issues')).toBe('/action-centre');
    expect(legacyExplorerRedirect('/explorer/pipeline')).toBe('/explorer');
  });

  test('legacy hub redirects', () => {
    expect(legacyOptimizationHubRedirect('/optimization-hub', '')).toBe('/action-centre?hasAction=1');
    expect(legacyOptimizationHubRedirect('/optimization-hub', '?tab=recommendations')).toBe('/action-centre');
  });
});
