import React, { useRef } from 'react';
import {
  Brush,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';

function useStableBrushData(data, dataKey, valueKey) {
  const dataRef = useRef(data);
  const signatureRef = useRef('');

  const signature = data?.map((row) => `${row[dataKey]}:${row[valueKey]}`).join('|') ?? '';
  if (signature !== signatureRef.current) {
    signatureRef.current = signature;
    dataRef.current = data;
  }

  return dataRef.current;
}

/**
 * Mini navigator chart with a Recharts Brush. Keep the brush on full data —
 * slicing the same chart data breaks `.recharts-brush-slide` dragging.
 */
export default function ChartBrushNavigator({
  data,
  dataKey,
  valueKey = 'cost',
  startIndex,
  endIndex,
  onRangeChange,
  height = 48,
}) {
  const stableData = useStableBrushData(data, dataKey, valueKey);

  if (!stableData?.length || stableData.length < 2) return null;

  return (
    <div className="chart-brush-nav" aria-label="Chart range selector">
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={stableData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
          <XAxis dataKey={dataKey} hide />
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Line
            type="monotone"
            dataKey={valueKey}
            stroke="var(--primary)"
            strokeWidth={1}
            dot={false}
            isAnimationActive={false}
          />
          <Brush
            dataKey={dataKey}
            height={28}
            stroke="var(--border)"
            fill="var(--surface2)"
            travellerWidth={12}
            startIndex={startIndex}
            endIndex={endIndex}
            onChange={onRangeChange}
            alwaysShowText={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
