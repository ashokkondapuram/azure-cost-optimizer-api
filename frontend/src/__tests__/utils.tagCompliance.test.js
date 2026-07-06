const REQUIRED_TAGS = ['env', 'owner', 'cost-center', 'project'];

function normaliseTags(raw) {
  if (!raw) return {};
  if (Array.isArray(raw)) return Object.fromEntries(raw.map(t => [t.tagName || t.key, t.tagValue || t.value]));
  return raw;
}

function compliance(tags) {
  const t = tags || {};
  const missing = REQUIRED_TAGS.filter(k => !t[k]);
  const score = Math.round(((REQUIRED_TAGS.length - missing.length) / REQUIRED_TAGS.length) * 100);
  return { missing, score };
}

describe('normaliseTags', () => {
  test('handles plain object', () => {
    expect(normaliseTags({ env: 'prod', owner: 'team-a' })).toEqual({ env: 'prod', owner: 'team-a' });
  });
  test('handles ARM array (tagName/tagValue)', () => {
    expect(normaliseTags([{ tagName: 'env', tagValue: 'dev' }])).toEqual({ env: 'dev' });
  });
  test('handles key/value alias', () => {
    expect(normaliseTags([{ key: 'env', value: 'staging' }])).toEqual({ env: 'staging' });
  });
  test('returns {} for null', () => { expect(normaliseTags(null)).toEqual({}); });
  test('returns {} for undefined', () => { expect(normaliseTags(undefined)).toEqual({}); });
});

describe('compliance', () => {
  test('100% when all tags present', () => {
    expect(compliance({ env:'p', owner:'x', 'cost-center':'CC', project:'p1' }).score).toBe(100);
  });
  test('0% when no tags', () => {
    const r = compliance({});
    expect(r.score).toBe(0);
    expect(r.missing).toHaveLength(4);
  });
  test('50% when 2 of 4 present', () => {
    expect(compliance({ env:'dev', owner:'me' }).score).toBe(50);
  });
  test('25% when 1 of 4 present', () => {
    expect(compliance({ env:'x' }).score).toBe(25);
  });
  test('handles null tags', () => {
    expect(compliance(null).score).toBe(0);
  });
});
