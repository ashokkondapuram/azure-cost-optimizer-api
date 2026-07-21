import { useEffect, useMemo, useState } from 'react';

/**
 * Controlled brush indices against the full dataset (not a sliced copy).
 */
export function useChartBrushRange(dataLength) {
  const [brushRange, setBrushRange] = useState(null);
  const maxIndex = Math.max(0, dataLength - 1);

  useEffect(() => {
    setBrushRange((prev) => {
      if (!prev) return null;
      if (prev[0] > maxIndex || prev[1] > maxIndex) return null;
      return prev;
    });
  }, [maxIndex]);

  const startIndex = brushRange?.[0] ?? 0;
  const endIndex = brushRange?.[1] ?? maxIndex;
  const isZoomed = brushRange != null && (startIndex > 0 || endIndex < maxIndex);

  const onBrushChange = (range) => {
    if (range?.startIndex == null || range?.endIndex == null) return;
    if (range.startIndex === 0 && range.endIndex >= maxIndex) {
      setBrushRange(null);
      return;
    }
    setBrushRange([range.startIndex, range.endIndex]);
  };

  const resetBrush = () => setBrushRange(null);

  return {
    brushRange,
    startIndex,
    endIndex,
    maxIndex,
    isZoomed,
    onBrushChange,
    resetBrush,
  };
}

export function applyBrushRange(data, startIndex, endIndex, maxIndex) {
  if (!data?.length) return data;
  if (startIndex <= 0 && endIndex >= maxIndex) return data;
  return data.slice(startIndex, endIndex + 1);
}

export function useBrushedChartData(data, startIndex, endIndex, maxIndex) {
  return useMemo(
    () => applyBrushRange(data, startIndex, endIndex, maxIndex),
    [data, startIndex, endIndex, maxIndex],
  );
}
