import { canViewNavPath } from './navAccess';

describe('navAccess sections', () => {
  const allPaths = [
    'section:overview',
    'section:advanced',
    'section:advanced:advanced-insights',
    'section:advanced:advanced-governance',
    'section:resources',
    'section:resources:compute',
    'section:resources:storage',
    'section:system',
    '/',
    '/costs',
    '/waste-heatmap',
    '/tag-compliance',
    '/vms',
    '/storage',
    '/settings',
  ];

  it('allows superusers regardless of policy', () => {
    expect(canViewNavPath('/waste-heatmap', [], { isSuperuser: true })).toBe(true);
  });

  it('blocks overview pages when the overview category is hidden', () => {
    const allowed = allPaths.filter((path) => path !== 'section:overview');
    expect(canViewNavPath('/', allowed)).toBe(false);
    expect(canViewNavPath('/costs', allowed)).toBe(false);
  });

  it('blocks only the hidden advanced subgroup', () => {
    const allowed = allPaths.filter((path) => path !== 'section:advanced:advanced-insights');
    expect(canViewNavPath('/waste-heatmap', allowed)).toBe(false);
    expect(canViewNavPath('/tag-compliance', allowed)).toBe(true);
  });

  it('blocks compute resources when that subgroup is hidden', () => {
    const allowed = allPaths.filter((path) => path !== 'section:resources:compute');
    expect(canViewNavPath('/vms', allowed)).toBe(false);
    expect(canViewNavPath('/storage', allowed)).toBe(true);
  });

  it('supports direct section checks', () => {
    expect(canViewNavPath('section:advanced', allPaths)).toBe(true);
    expect(canViewNavPath('section:advanced', allPaths.filter((p) => p !== 'section:advanced'))).toBe(false);
  });
});
