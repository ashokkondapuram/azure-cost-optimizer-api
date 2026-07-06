function normalizeListResponse(data) {
  if (Array.isArray(data))                return data;
  if (Array.isArray(data?.value))         return data.value;
  if (Array.isArray(data?.items))         return data.items;
  if (Array.isArray(data?.subscriptions)) return data.subscriptions;
  return [];
}

function normalizePagedResponse(data) {
  if (data && Array.isArray(data.items) && typeof data.total === 'number') {
    return { items:data.items, total:data.total, limit:data.limit, offset:data.offset, has_more:Boolean(data.has_more) };
  }
  const items = normalizeListResponse(data);
  return { items, total:items.length, limit:items.length, offset:0, has_more:false };
}

describe('normalizeListResponse', () => {
  test('passes through plain array', () => { const a=[{id:1}]; expect(normalizeListResponse(a)).toBe(a); });
  test('extracts .value (ARM)', () => { expect(normalizeListResponse({value:[{id:'a'}]})).toEqual([{id:'a'}]); });
  test('extracts .items (DB paged)', () => { expect(normalizeListResponse({items:[{id:'b'}],total:1})).toEqual([{id:'b'}]); });
  test('extracts .subscriptions', () => { expect(normalizeListResponse({subscriptions:[{subscriptionId:'x'}]})).toEqual([{subscriptionId:'x'}]); });
  test('returns [] for null', () => { expect(normalizeListResponse(null)).toEqual([]); });
  test('returns [] for undefined', () => { expect(normalizeListResponse(undefined)).toEqual([]); });
  test('returns [] for unknown shape', () => { expect(normalizeListResponse({data:[]})).toEqual([]); });
});

describe('normalizePagedResponse', () => {
  test('paged envelope path', () => {
    const r = normalizePagedResponse({items:[1,2],total:2,limit:50,offset:0,has_more:false});
    expect(r.items).toEqual([1,2]); expect(r.total).toBe(2);
  });
  test('falls back to plain array', () => {
    const r = normalizePagedResponse([{id:1}]);
    expect(r.items).toEqual([{id:1}]); expect(r.total).toBe(1);
  });
  test('has_more coerced to boolean', () => {
    expect(normalizePagedResponse({items:[],total:0,has_more:1}).has_more).toBe(true);
  });
});
