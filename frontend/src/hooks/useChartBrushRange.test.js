import { applyBrushRange } from '../hooks/useChartBrushRange';

describe('applyBrushRange', () => {
  test('returns full data when range covers all points', () => {
    const data = [{ id: 0 }, { id: 1 }, { id: 2 }, { id: 3 }];
    expect(applyBrushRange(data, 0, 3, 3)).toEqual(data);
  });

  test('slices by index when zoomed', () => {
    const data = [{ id: 0 }, { id: 1 }, { id: 2 }, { id: 3 }];
    expect(applyBrushRange(data, 1, 2, 3).map((r) => r.id)).toEqual([1, 2]);
  });
});
