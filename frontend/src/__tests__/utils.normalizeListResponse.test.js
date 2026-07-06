// ============================================================
// utils.normalizeListResponse — rigorous tests
// Mirrors api/azure.js envelope normalisation utilities
// ============================================================

function normalizeListResponse(data) {
  if (Array.isArray(data))                return data;
  if (Array.isArray(data?.value))         return data.value;
  if (Array.isArray(data?.items))         return data.items;
  if (Array.isArray(data?.subscriptions)) return data.subscriptions;
  return [];
}

function normalizePagedResponse(data) {
  if (data && Array.isArray(data.items) && typeof data.total === 'number') {
    return {
      items:    data.items,
      total:    data.total,
      limit:    data.limit,
      offset:   data.offset,
      has_more: Boolean(data.has_more),
    };
  }
  const items = normalizeListResponse(data);
  return { items, total: items.length, limit: items.length, offset: 0, has_more: false };
}

// ── normalizeListResponse — array pass-through ───────────────
describe('normalizeListResponse — plain array', () => {
  test('returns the same array reference (no copy)', () => {
    const a = [{ id:1 }];
    expect(normalizeListResponse(a)).toBe(a);
  });
  test('empty array returned as-is', () => {
    expect(normalizeListResponse([])).toEqual([]);
  });
  test('nested array not unwrapped (first level only)', () => {
    const a = [[1,2],[3,4]];
    expect(normalizeListResponse(a)).toBe(a);
  });
});

// ── normalizeListResponse — envelope shapes ──────────────────
describe('normalizeListResponse — .value envelope (ARM)', () => {
  test('extracts .value array', () => {
    expect(normalizeListResponse({ value:[{id:'a'}] })).toEqual([{id:'a'}]);
  });
  test('empty .value array', () => {
    expect(normalizeListResponse({ value:[] })).toEqual([]);
  });
  test('.value non-array ignored → []', () => {
    expect(normalizeListResponse({ value:'not-array' })).toEqual([]);
  });
});

describe('normalizeListResponse — .items envelope (paged DB)', () => {
  test('extracts .items', () => {
    expect(normalizeListResponse({ items:[{id:'b'}], total:1 })).toEqual([{id:'b'}]);
  });
  test('empty .items', () => {
    expect(normalizeListResponse({ items:[] })).toEqual([]);
  });
});

describe('normalizeListResponse — .subscriptions envelope', () => {
  test('extracts .subscriptions', () => {
    expect(normalizeListResponse({ subscriptions:[{subscriptionId:'x'}] })).toEqual([{subscriptionId:'x'}]);
  });
  test('empty .subscriptions', () => {
    expect(normalizeListResponse({ subscriptions:[] })).toEqual([]);
  });
});

// ── normalizeListResponse — null/undefined/unknown ───────────
describe('normalizeListResponse — unknown/null shapes', () => {
  test('null → []', () => { expect(normalizeListResponse(null)).toEqual([]); });
  test('undefined → []', () => { expect(normalizeListResponse(undefined)).toEqual([]); });
  test('number → []', () => { expect(normalizeListResponse(42)).toEqual([]); });
  test('string → []', () => { expect(normalizeListResponse('[]')).toEqual([]); });
  test('object without known keys → []', () => {
    expect(normalizeListResponse({ data:[], results:[] })).toEqual([]);
  });
  test('object with non-array .value → []', () => {
    expect(normalizeListResponse({ value: null })).toEqual([]);
  });
});

// ── normalizeListResponse — envelope priority ────────────────
describe('normalizeListResponse — envelope priority', () => {
  test('plain array wins over envelope keys', () => {
    // If the data itself is an array, return it even if it has a .value property
    const a = Object.assign([{ id:1 }], { value:[{ id:99 }] });
    expect(normalizeListResponse(a)).toBe(a);
  });
  test('.value checked before .items', () => {
    expect(normalizeListResponse({ value:[{id:'v'}], items:[{id:'i'}] })).toEqual([{id:'v'}]);
  });
  test('.items checked before .subscriptions', () => {
    expect(normalizeListResponse({ items:[{id:'i'}], subscriptions:[{id:'s'}] })).toEqual([{id:'i'}]);
  });
});

// ── normalizePagedResponse ────────────────────────────────────
describe('normalizePagedResponse — paged envelope', () => {
  test('returns items, total, limit, offset, has_more', () => {
    const r = normalizePagedResponse({ items:[1,2], total:2, limit:50, offset:0, has_more:false });
    expect(r).toMatchObject({ items:[1,2], total:2, limit:50, offset:0, has_more:false });
  });
  test('has_more coerced from truthy number', () => {
    expect(normalizePagedResponse({ items:[], total:0, has_more:1 }).has_more).toBe(true);
  });
  test('has_more coerced from falsy 0', () => {
    expect(normalizePagedResponse({ items:[], total:0, has_more:0 }).has_more).toBe(false);
  });
  test('has_more coerced from string "true"', () => {
    // Boolean("true") === true
    expect(normalizePagedResponse({ items:[], total:0, has_more:'true' }).has_more).toBe(true);
  });
});

describe('normalizePagedResponse — fallback path', () => {
  test('plain array → items=array, total=length, has_more=false', () => {
    const r = normalizePagedResponse([{id:1},{id:2}]);
    expect(r.items).toEqual([{id:1},{id:2}]);
    expect(r.total).toBe(2);
    expect(r.has_more).toBe(false);
    expect(r.offset).toBe(0);
  });
  test('ARM .value envelope unwrapped correctly', () => {
    const r = normalizePagedResponse({ value:[{id:'a'},{id:'b'}] });
    expect(r.items).toEqual([{id:'a'},{id:'b'}]);
    expect(r.total).toBe(2);
  });
  test('null → empty paged response', () => {
    const r = normalizePagedResponse(null);
    expect(r.items).toEqual([]);
    expect(r.total).toBe(0);
    expect(r.has_more).toBe(false);
  });
  test('paged envelope requires BOTH items array AND numeric total', () => {
    // items present but total is a string — must fall back
    const r = normalizePagedResponse({ items:[1,2], total:'2' });
    // total is not typeof 'number', so fallback path; items.length = 2
    expect(r.total).toBe(2);
  });
});

describe('normalizePagedResponse — shape invariants', () => {
  const REQUIRED = ['items','total','limit','offset','has_more'];
  test('always returns all required keys (paged path)', () => {
    const r = normalizePagedResponse({ items:[1], total:1 });
    REQUIRED.forEach(k => expect(r).toHaveProperty(k));
  });
  test('always returns all required keys (fallback path)', () => {
    const r = normalizePagedResponse([]);
    REQUIRED.forEach(k => expect(r).toHaveProperty(k));
  });
  test('items is always an array', () => {
    [null, undefined, [], [1], { value:[1] }, { items:[1], total:1 }].forEach(input => {
      expect(Array.isArray(normalizePagedResponse(input).items)).toBe(true);
    });
  });
  test('has_more is always a boolean', () => {
    [null, [], { items:[1], total:1, has_more:1 }, { items:[], total:0 }].forEach(input => {
      expect(typeof normalizePagedResponse(input).has_more).toBe('boolean');
    });
  });
});
