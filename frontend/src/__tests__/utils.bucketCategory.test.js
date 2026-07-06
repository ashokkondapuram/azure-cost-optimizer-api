const SEVERITIES = ['CRITICAL','HIGH','MEDIUM','LOW','INFO'];

function bucketCategory(finding) {
  const raw = (finding.component || finding.resource_type || finding.category || '').toLowerCase();
  if (/vm|compute|virtual.machine|vmss/.test(raw))           return 'Compute';
  if (/storage|disk|snapshot/.test(raw))                     return 'Storage';
  if (/network|ip|vnet|nic|loadbal|gateway|nsg/.test(raw))   return 'Network';
  if (/aks|kubernetes|k8s|container/.test(raw))              return 'AKS';
  if (/sql|postgres|cosmos|redis|database|db/.test(raw))     return 'Database';
  if (/keyvault|identity|auth|security/.test(raw))           return 'Identity';
  return null;
}

function bucketSeverity(finding) {
  const s = (finding.severity || '').toUpperCase();
  return SEVERITIES.includes(s) ? s : 'INFO';
}

describe('bucketCategory', () => {
  test.each([
    [{ component: 'vm' },           'Compute'],
    [{ resource_type: 'VMSS' },     'Compute'],
    [{ component: 'disk' },         'Storage'],
    [{ component: 'snapshot' },     'Storage'],
    [{ component: 'storage' },      'Storage'],
    [{ component: 'vnet' },         'Network'],
    [{ component: 'loadbalancer' }, 'Network'],
    [{ component: 'nsg' },          'Network'],
    [{ component: 'aks' },          'AKS'],
    [{ component: 'kubernetes' },   'AKS'],
    [{ component: 'cosmosdb' },     'Database'],
    [{ component: 'postgresql' },   'Database'],
    [{ component: 'redis' },        'Database'],
    [{ component: 'sql' },          'Database'],
    [{ component: 'keyvault' },     'Identity'],
    [{ component: 'identity' },     'Identity'],
    [{ component: 'unknown-svc' },  null],
    [{},                            null],
  ])('bucketCategory(%j) === %s', (finding, expected) => {
    expect(bucketCategory(finding)).toBe(expected);
  });
});

describe('bucketSeverity', () => {
  test.each([
    [{ severity: 'CRITICAL' }, 'CRITICAL'],
    [{ severity: 'high' },     'HIGH'],
    [{ severity: 'Medium' },   'MEDIUM'],
    [{ severity: 'LOW' },      'LOW'],
    [{ severity: 'info' },     'INFO'],
    [{ severity: 'bogus' },    'INFO'],
    [{},                       'INFO'],
  ])('bucketSeverity(%j) === %s', (finding, expected) => {
    expect(bucketSeverity(finding)).toBe(expected);
  });
});
