import React, { memo } from 'react';
import { Line, LineChart } from 'recharts';

function MiniSparkline({ data, dataKey = 'cost', stroke = 'var(--primary)' }) {
  if (!data?.length) return null;
  return (
    <div className="stat-card__sparkline" aria-hidden>
      <LineChart width={80} height={28} data={data}>
        <Line
          type="monotone"
          dataKey={dataKey}
          stroke={stroke}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </div>
  );
}

export default memo(MiniSparkline);
