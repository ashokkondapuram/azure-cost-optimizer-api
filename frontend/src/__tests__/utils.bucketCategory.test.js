// ============================================================
// utils.bucketCategory — rigorous tests
// Mirrors WasteHeatmap.jsx: bucketCategory + bucketSeverity + buildMatrix
// ============================================================

const CATEGORIES = ['Compute','Storage','Network','AKS','Database','Identity'];
const SEVERITIES  = ['CRITICAL','HIGH','MEDIUM','LOW','INFO'];

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

function buildMatrix(findings) {
  const matrix = {};
  CATEGORIES.forEach(c => {
    matrix[c] = {};
    SEVERITIES.forEach(s => { matrix[c][s] = { count: 0, waste: 0 }; });
  });
  findings.forEach(f => {
    const cat = bucketCategory(f);
    const sev = bucketSeverity(f);
    if (!cat) return;
    matrix[cat][sev].count  += 1;
    matrix[cat][sev].waste  += Number(f.estimated_monthly_savings || f.savings || 0);
  });
  return matrix;
}

// ── bucketCategory: correct bucket ──────────────────────────
describe('bucketCategory — canonical inputs', () => {
  test.each([
    // Compute
    [{ component: 'vm' },                     'Compute'],
    [{ component: 'VIRTUAL-MACHINE' },        'Compute'],  // case-insensitive
    [{ component: 'compute' },                'Compute'],
    [{ resource_type: 'VMSS' },               'Compute'],
    [{ resource_type: 'Microsoft.Compute/virtualMachines' }, 'Compute'],
    // Storage
    [{ component: 'disk' },                   'Storage'],
    [{ component: 'snapshot' },               'Storage'],
    [{ component: 'storage' },                'Storage'],
    [{ resource_type: 'Microsoft.Storage/storageAccounts' }, 'Storage'],
    // Network
    [{ component: 'vnet' },                   'Network'],
    [{ component: 'loadbalancer' },           'Network'],
    [{ component: 'LOADBALANCER' },           'Network'],  // case
    [{ component: 'nsg' },                    'Network'],
    [{ component: 'gateway' },                'Network'],
    [{ component: 'publicip' },               'Network'],  // "ip" substring
    [{ component: 'nic' },                    'Network'],
    // AKS
    [{ component: 'aks' },                    'AKS'],
    [{ component: 'kubernetes' },             'AKS'],
    [{ component: 'container' },              'AKS'],
    [{ resource_type: 'k8s-cluster' },        'AKS'],
    // Database
    [{ component: 'cosmosdb' },               'Database'],
    [{ component: 'postgresql' },             'Database'],
    [{ component: 'redis' },                  'Database'],
    [{ component: 'sql' },                    'Database'],
    [{ component: 'database' },               'Database'],
    // Identity
    [{ component: 'keyvault' },               'Identity'],
    [{ component: 'identity' },               'Identity'],
    [{ component: 'auth' },                   'Identity'],
    [{ component: 'security' },               'Identity'],
    // Null
    [{ component: 'unknown-svc' },            null],
    [{},                                      null],
    [{ component: '' },                       null],
    [{ component: null },                     null],
  ])('bucketCategory(%j) → %s', (finding, expected) => {
    expect(bucketCategory(finding)).toBe(expected);
  });
});

// ── bucketCategory: field priority ──────────────────────────
describe('bucketCategory — field priority', () => {
  test('component wins over resource_type', () => {
    // component="disk" (Storage) but resource_type="vm" (Compute) → Storage wins
    expect(bucketCategory({ component: 'disk', resource_type: 'vm' })).toBe('Storage');
  });
  test('resource_type used when component absent', () => {
    expect(bucketCategory({ resource_type: 'vm' })).toBe('Compute');
  });
  test('category used as last resort', () => {
    expect(bucketCategory({ category: 'redis' })).toBe('Database');
  });
  test('component empty string → falls through to resource_type', () => {
    expect(bucketCategory({ component: '', resource_type: 'storage' })).toBe('Storage');
  });
});

// ── bucketCategory: regex does NOT false-match ───────────────
describe('bucketCategory — no false positives', () => {
  test('"loadbalancer" does NOT match Database', () => {
    expect(bucketCategory({ component: 'loadbalancer' })).not.toBe('Database');
  });
  test('"dbgateway" hits Network (gateway) before Database (db)', () => {
    // "dbgateway" contains "gateway" AND "db" — Network regex is checked first
    expect(bucketCategory({ component: 'dbgateway' })).toBe('Network');
  });
  test('"storage" does not match Network (no network|ip|… match)', () => {
    expect(bucketCategory({ component: 'storage' })).toBe('Storage');
  });
  test('"vmss" goes to Compute, not null', () => {
    expect(bucketCategory({ component: 'vmss' })).toBe('Compute');
  });
});

// ── bucketSeverity ───────────────────────────────────────────
describe('bucketSeverity', () => {
  test.each([
    [{ severity: 'CRITICAL' }, 'CRITICAL'],
    [{ severity: 'critical' }, 'CRITICAL'],
    [{ severity: 'Critical' }, 'CRITICAL'],
    [{ severity: 'high' },     'HIGH'],
    [{ severity: 'HIGH' },     'HIGH'],
    [{ severity: 'Medium' },   'MEDIUM'],
    [{ severity: 'MEDIUM' },   'MEDIUM'],
    [{ severity: 'low' },      'LOW'],
    [{ severity: 'LOW' },      'LOW'],
    [{ severity: 'info' },     'INFO'],
    [{ severity: 'INFO' },     'INFO'],
    [{ severity: 'bogus' },    'INFO'],
    [{ severity: 'none' },     'INFO'],
    [{ severity: '' },         'INFO'],
    [{},                       'INFO'],
    [{ severity: null },       'INFO'],
  ])('bucketSeverity(%j) → %s', (finding, expected) => {
    expect(bucketSeverity(finding)).toBe(expected);
  });
});

// ── buildMatrix ──────────────────────────────────────────────
describe('buildMatrix', () => {
  test('returns a matrix with all category×severity cells initialised to 0', () => {
    const m = buildMatrix([]);
    CATEGORIES.forEach(c => {
      SEVERITIES.forEach(s => {
        expect(m[c][s]).toEqual({ count: 0, waste: 0 });
      });
    });
  });

  test('increments count and accumulates waste correctly', () => {
    const findings = [
      { component: 'vm',    severity: 'HIGH',   estimated_monthly_savings: 100 },
      { component: 'vm',    severity: 'HIGH',   estimated_monthly_savings: 50  },
      { component: 'disk',  severity: 'MEDIUM', savings: 200 },
    ];
    const m = buildMatrix(findings);
    expect(m['Compute']['HIGH'].count).toBe(2);
    expect(m['Compute']['HIGH'].waste).toBe(150);
    expect(m['Storage']['MEDIUM'].count).toBe(1);
    expect(m['Storage']['MEDIUM'].waste).toBe(200);
  });

  test('findings with unknown category are skipped (count stays 0)', () => {
    const findings = [{ component: 'mystery-service', severity: 'CRITICAL' }];
    const m = buildMatrix(findings);
    const totalCount = CATEGORIES.flatMap(c => SEVERITIES.map(s => m[c][s].count)).reduce((a,b)=>a+b,0);
    expect(totalCount).toBe(0);
  });

  test('waste uses estimated_monthly_savings before savings fallback', () => {
    const m = buildMatrix([{ component: 'vm', severity: 'LOW', estimated_monthly_savings: 99, savings: 1 }]);
    expect(m['Compute']['LOW'].waste).toBe(99);
  });

  test('waste defaults to 0 when neither savings field present', () => {
    const m = buildMatrix([{ component: 'vm', severity: 'CRITICAL' }]);
    expect(m['Compute']['CRITICAL'].waste).toBe(0);
  });

  test('non-numeric savings coerced via Number()', () => {
    const m = buildMatrix([{ component: 'vm', severity: 'INFO', estimated_monthly_savings: '75.5' }]);
    expect(m['Compute']['INFO'].waste).toBeCloseTo(75.5);
  });

  test('NaN savings treated as 0 (Number(undefined) = NaN → 0)', () => {
    const m = buildMatrix([{ component: 'vm', severity: 'INFO', estimated_monthly_savings: undefined }]);
    // Number(undefined) is NaN; Number(NaN) when used in += is NaN; we accept 0
    expect(m['Compute']['INFO'].waste).toBe(0);
  });
});
