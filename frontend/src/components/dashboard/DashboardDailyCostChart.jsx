import React, { useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatCurrency } from '../../utils/format';
import { formatChartAxis } from '../../utils/costCurrency';
import { buildMtdComparisonSeries } from '../../utils/costComparisonChart';
import TrendBadge from '../visual/TrendBadge';
import ChartBrushNavigator from '../charts/ChartBrushNavigator';
import { useChartBrushRange, useBrushedChartData } from '../../hooks/useChartBrushRange';

function CostTooltip({ active, payload, label, currency, compareMode }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__date">{label}</div>
      {payload.map((row) => (
        <div key={row.dataKey} className="chart-tooltip__value">
          {row.name}: {formatCurrency(row.value, { currency, decimals: 0 })}
        </div>
      ))}
    </div>
  );
}

export default function DashboardDailyCostChart({
  chartData,
  anomalies,
  budgetLine,
  currency,
  chartCurrency,
  dailyPoints = [],
  monthlyComparison = null,
}) {
  const [hiddenSeries, setHiddenSeries] = useState({});
  const [viewMode, setViewMode] = useState('daily');

  const { series: mtdSeries, comparison } = useMemo(
    () => buildMtdComparisonSeries(dailyPoints, monthlyComparison),
    [dailyPoints, monthlyComparison],
  );

  const activeData = viewMode === 'mtd' && mtdSeries.length ? mtdSeries : chartData;
  const brushSource = viewMode === 'daily' ? chartData : [];
  const {
    startIndex,
    endIndex,
    maxIndex,
    isZoomed,
    onBrushChange,
    resetBrush,
  } = useChartBrushRange(brushSource.length);
  const visibleChartData = useBrushedChartData(
    activeData,
    viewMode === 'daily' ? startIndex : 0,
    viewMode === 'daily' ? endIndex : Math.max(0, activeData.length - 1),
    viewMode === 'daily' ? maxIndex : Math.max(0, activeData.length - 1),
  );

  if (!chartData?.length && !mtdSeries.length) return null;

  const mtdDelta = comparison?.mtd_delta_usd;
  const compareLabel = viewMode === 'mtd' ? 'MTD vs last month' : 'Daily spend';

  return (
    <div className="chart-slot">
      <div className="cost-trend-chart__toolbar">
        <div className="cost-trend-chart__view-toggle" role="group" aria-label="Chart view">
          <button
            type="button"
            className={`btn btn-ghost btn-sm${viewMode === 'daily' ? ' active' : ''}`}
            onClick={() => { setViewMode('daily'); resetBrush(); }}
          >
            Daily
          </button>
          <button
            type="button"
            className={`btn btn-ghost btn-sm${viewMode === 'mtd' ? ' active' : ''}`}
            onClick={() => { setViewMode('mtd'); resetBrush(); }}
            disabled={!mtdSeries.length}
          >
            MTD vs last month
          </button>
        </div>
        {mtdDelta != null && Number(mtdDelta) !== 0 && (
          <span className="cost-trend-chart__delta">
            <TrendBadge deltaAmount={mtdDelta} currency={chartCurrency} invert />
            <span className="text-muted text-sm">vs same period last month</span>
          </span>
        )}
        <div className="cost-trend-chart__legend-toggles" role="group" aria-label="Chart series">
          {viewMode === 'daily' ? (
            <>
              <button
                type="button"
                className={`cost-trend-chart__legend-btn${hiddenSeries.spend ? '' : ' cost-trend-chart__legend-btn--active'}`}
                onClick={() => setHiddenSeries((prev) => ({ ...prev, spend: !prev.spend }))}
              >
                Spend
              </button>
              <button
                type="button"
                className={`cost-trend-chart__legend-btn${hiddenSeries.forecast ? '' : ' cost-trend-chart__legend-btn--active'}`}
                onClick={() => setHiddenSeries((prev) => ({ ...prev, forecast: !prev.forecast }))}
              >
                Forecast
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className={`cost-trend-chart__legend-btn${hiddenSeries.mtd ? '' : ' cost-trend-chart__legend-btn--active'}`}
                onClick={() => setHiddenSeries((prev) => ({ ...prev, mtd: !prev.mtd }))}
              >
                This month
              </button>
              <button
                type="button"
                className={`cost-trend-chart__legend-btn${hiddenSeries.prior ? '' : ' cost-trend-chart__legend-btn--active'}`}
                onClick={() => setHiddenSeries((prev) => ({ ...prev, prior: !prev.prior }))}
              >
                Last month
              </button>
            </>
          )}
        </div>
        {isZoomed && viewMode === 'daily' && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={resetBrush}>
            Reset zoom
          </button>
        )}
      </div>
      <p className="cost-trend-chart__subtitle text-muted text-sm">{compareLabel}</p>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={visibleChartData}>
          <defs>
            <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.15} />
              <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="priorMtdGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--text3)" stopOpacity={0.12} />
              <stop offset="95%" stopColor="var(--text3)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey={viewMode === 'mtd' ? 'label' : 'date'}
            tick={{ fill: 'var(--text3)', fontSize: 10 }}
          />
          <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} tickFormatter={(v) => formatChartAxis(v, currency)} />
          <Tooltip content={<CostTooltip currency={chartCurrency} compareMode={viewMode} />} />
          <Legend />
          {viewMode === 'daily' && !hiddenSeries.spend && (
            <Area
              type="monotone"
              dataKey="cost"
              name="Spend"
              stroke="var(--primary)"
              strokeWidth={2}
              fill="url(#costGradient)"
              dot={false}
            />
          )}
          {viewMode === 'daily' && !hiddenSeries.forecast && (
            <Line
              type="monotone"
              dataKey="forecast"
              name="Forecast"
              stroke="var(--warning)"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              connectNulls
            />
          )}
          {viewMode === 'mtd' && !hiddenSeries.mtd && (
            <Area
              type="monotone"
              dataKey="mtd"
              name="This month"
              stroke="var(--primary)"
              strokeWidth={2}
              fill="url(#costGradient)"
              dot={false}
            />
          )}
          {viewMode === 'mtd' && !hiddenSeries.prior && (
            <Line
              type="monotone"
              dataKey="priorMtd"
              name="Last month"
              stroke="var(--text3)"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
            />
          )}
          {viewMode === 'daily' && budgetLine != null && (
            <ReferenceLine
              y={budgetLine / 30}
              stroke="var(--danger)"
              strokeDasharray="6 4"
              label={{ value: 'Budget', fill: 'var(--danger)', fontSize: 10 }}
            />
          )}
          {viewMode === 'daily' && anomalies.map((d) => (
            <ReferenceDot
              key={d.date}
              x={d.date}
              y={d.cost}
              r={4}
              fill="var(--danger)"
              stroke="none"
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
      {viewMode === 'daily' && (
        <ChartBrushNavigator
          data={chartData}
          dataKey="date"
          valueKey="cost"
          startIndex={startIndex}
          endIndex={endIndex}
          onRangeChange={onBrushChange}
        />
      )}
    </div>
  );
}
