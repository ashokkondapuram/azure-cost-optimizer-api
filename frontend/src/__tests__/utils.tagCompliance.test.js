// ============================================================
// utils.tagCompliance — rigorous tests
// Mirrors TagCompliancePage.jsx: normaliseTags + compliance
// ============================================================

const REQUIRED_TAGS = ['env', 'owner', 'cost-center', 'project'];

function normaliseTags(raw) {
  if (!raw) return {};
  if (Array.isArray(raw)) {
    return Object.fromEntries(raw.map(t => [t.tagName || t.key, t.tagValue || t.value]));
  }
  return raw;
}

function compliance(tags) {
  const t       = tags || {};
  const missing = REQUIRED_TAGS.filter(k => !t[k]);
  const score   = Math.round(((REQUIRED_TAGS.length - missing.length) / REQUIRED_TAGS.length) * 100);
  return { missing, score };
}

// ── normaliseTags ─────────────────────────────────────────────
describe('normaliseTags — passthrough', () => {
  test('plain object returned as-is', () => {
    const obj = { env: 'prod', owner: 'team-a' };
    expect(normaliseTags(obj)).toEqual(obj);
  });
  test('preserves extra non-required tags', () => {
    expect(normaliseTags({ env:'prod', custom:'value' })).toEqual({ env:'prod', custom:'value' });
  });
  test('empty object', () => {
    expect(normaliseTags({})).toEqual({});
  });
});

describe('normaliseTags — ARM array (tagName/tagValue)', () => {
  test('single tag', () => {
    expect(normaliseTags([{ tagName:'env', tagValue:'dev' }])).toEqual({ env:'dev' });
  });
  test('multiple tags', () => {
    expect(normaliseTags([
      { tagName:'env', tagValue:'prod' },
      { tagName:'owner', tagValue:'infra' },
    ])).toEqual({ env:'prod', owner:'infra' });
  });
  test('empty array → empty object', () => {
    expect(normaliseTags([])).toEqual({});
  });
  test('last-write wins on duplicate tagNames', () => {
    const result = normaliseTags([
      { tagName:'env', tagValue:'dev' },
      { tagName:'env', tagValue:'prod' },
    ]);
    expect(result.env).toBe('prod');
  });
});

describe('normaliseTags — key/value alias', () => {
  test('key/value shape', () => {
    expect(normaliseTags([{ key:'env', value:'staging' }])).toEqual({ env:'staging' });
  });
  test('tagName wins over key when both present', () => {
    expect(normaliseTags([{ tagName:'env', key:'other', tagValue:'prod', value:'x' }]))
      .toEqual({ env:'prod' });
  });
});

describe('normaliseTags — null/undefined', () => {
  test('null → {}', () => { expect(normaliseTags(null)).toEqual({}); });
  test('undefined → {}', () => { expect(normaliseTags(undefined)).toEqual({}); });
  test('false → {}', () => { expect(normaliseTags(false)).toEqual({}); });
  test('0 → {}', () => { expect(normaliseTags(0)).toEqual({}); });
});

// ── compliance ────────────────────────────────────────────────
describe('compliance — score', () => {
  test('100% — all 4 tags present', () => {
    expect(compliance({ env:'p', owner:'x', 'cost-center':'CC', project:'p1' }).score).toBe(100);
  });
  test('75% — 3 of 4 present', () => {
    expect(compliance({ env:'p', owner:'x', 'cost-center':'CC' }).score).toBe(75);
  });
  test('50% — 2 of 4 present', () => {
    expect(compliance({ env:'dev', owner:'me' }).score).toBe(50);
  });
  test('25% — 1 of 4 present', () => {
    expect(compliance({ env:'x' }).score).toBe(25);
  });
  test('0% — no tags', () => {
    expect(compliance({}).score).toBe(0);
  });
});

describe('compliance — missing list', () => {
  test('empty missing when all tags present', () => {
    expect(compliance({ env:'p', owner:'x', 'cost-center':'CC', project:'p1' }).missing).toEqual([]);
  });
  test('lists all 4 when no tags', () => {
    const { missing } = compliance({});
    expect(missing).toHaveLength(4);
    expect(missing).toContain('env');
    expect(missing).toContain('owner');
    expect(missing).toContain('cost-center');
    expect(missing).toContain('project');
  });
  test('lists only missing tags (partial)', () => {
    const { missing } = compliance({ env:'x', project:'p' });
    expect(missing).toEqual(expect.arrayContaining(['owner','cost-center']));
    expect(missing).not.toContain('env');
    expect(missing).not.toContain('project');
  });
});

describe('compliance — null/undefined input', () => {
  test('null tags → 0% score', () => { expect(compliance(null).score).toBe(0); });
  test('undefined tags → 0% score', () => { expect(compliance(undefined).score).toBe(0); });
  test('null tags → all 4 missing', () => { expect(compliance(null).missing).toHaveLength(4); });
});

describe('compliance — edge cases', () => {
  test('empty string tag value treated as missing (falsy)', () => {
    expect(compliance({ env: '', owner: 'me', 'cost-center':'CC', project:'p' }).missing).toContain('env');
  });
  test('0 tag value treated as missing (falsy)', () => {
    expect(compliance({ env: 0, owner:'me', 'cost-center':'CC', project:'p' }).missing).toContain('env');
  });
  test('extra tags do not affect score', () => {
    expect(compliance({ env:'p', owner:'x', 'cost-center':'CC', project:'p1', extra:'foo' }).score).toBe(100);
  });
});

// ── round-trip: normaliseTags → compliance ────────────────────
describe('normaliseTags → compliance round-trip', () => {
  test('ARM array all required → 100%', () => {
    const raw = [
      { tagName:'env',         tagValue:'prod' },
      { tagName:'owner',       tagValue:'team-a' },
      { tagName:'cost-center', tagValue:'CC-01' },
      { tagName:'project',     tagValue:'horizon' },
    ];
    expect(compliance(normaliseTags(raw)).score).toBe(100);
  });
  test('ARM array 2 required → 50%', () => {
    const raw = [
      { tagName:'env', tagValue:'dev' },
      { tagName:'owner', tagValue:'me' },
    ];
    expect(compliance(normaliseTags(raw)).score).toBe(50);
  });
});
