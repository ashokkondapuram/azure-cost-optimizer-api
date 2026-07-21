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

function CostTooltip({ active, payload, label, currency }) {
  if (!active || !payload?.length) return null;
  const visible = payload.filter((row) => row.value != null && !Number.isNaN(Number(row.value)));
  const total = visible.reduce((sum, row) => sum + Number(row.value || 0), 0);
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__date">{label}</div>
      {visible.map((row) => (
        <div key={row.dataKey} className="chart-tooltip__value" style={{ color: row.color }}>
          {row.name}: {formatCurrency(row.value, { currency, decimals: 0 })}
        </div>
      ))}
      {visible.length > 1 && (
        <div className="chart-tooltip__forecast">
          Total: {formatCurrency(total, { currency, decimals: 0 })}
        </div>
      )}
    </div>
  );
}

const LEGEND_SERIES_KEYS = {
  cost: 'spend',
  forecast: 'forecast',
  mtd: 'mtd',
  priorMtd: 'prior',
};

function legendSeriesHidden(hiddenSeries, dataKey) {
  const key = LEGEND_SERIES_KEYS[dataKey];
  return key ? !!hiddenSeries[key] : false;
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

  const toggleSeries = (dataKey) => {
    const key = LEGEND_SERIES_KEYS[dataKey];
    if (!key) return;
    setHiddenSeries((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleLegendClick = (entry) => {
    toggleSeries(entry.dataKey);
  };

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
                onClick={() => toggleSeries('cost')}
              >
                Spend
              </button>
              <button
                type="button"
                className={`cost-trend-chart__legend-btn${hiddenSeries.forecast ? '' : ' cost-trend-chart__legend-btn--active'}`}
                onClick={() => toggleSeries('forecast')}
              >
                Forecast
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className={`cost-trend-chart__legend-btn${hiddenSeries.mtd ? '' : ' cost-trend-chart__legend-btn--active'}`}
                onClick={() => toggleSeries('mtd')}
              >
                This month
              </button>
              <button
                type="button"
                className={`cost-trend-chart__legend-btn${hiddenSeries.prior ? '' : ' cost-trend-chart__legend-btn--active'}`}
                onClick={() => toggleSeries('priorMtd')}
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
              <stop offset="5%" stopColor="var(--chart-series-1)" stopOpacity={0.15} />
              <stop offset="95%" stopColor="var(--chart-series-1)" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="priorMtdGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--chart-prior-period)" stopOpacity={0.12} />
              <stop offset="95%" stopColor="var(--chart-prior-period)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis
            dataKey={viewMode === 'mtd' ? 'label' : 'date'}
            tick={{ fill: 'var(--chart-axis)', fontSize: 10 }}
          />
          <YAxis tick={{ fill: 'var(--chart-axis)', fontSize: 10 }} tickFormatter={(v) => formatChartAxis(v, currency)} />
          <Tooltip cursor={{ fill: 'transparent' }} content={<CostTooltip currency={chartCurrency} />} />
          <Legend
            onClick={handleLegendClick}
            wrapperStyle={{ cursor: 'pointer', fontSize: '0.75rem' }}
            formatter={(value, entry) => (
              <span style={{ opacity: legendSeriesHidden(hiddenSeries, entry.dataKey) ? 0.4 : 1 }}>
                {value}
              </span>
            )}
          />
          {viewMode === 'daily' && !hiddenSeries.spend && (
            <Area
              type="monotone"
              dataKey="cost"
              name="Spend"
              stroke="var(--chart-series-1)"
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
              stroke="var(--chart-forecast)"
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
              stroke="var(--chart-series-1)"
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
              stroke="var(--chart-prior-period)"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
            />
          )}
          {viewMode === 'daily' && budgetLine != null && (
            <ReferenceLine
              y={budgetLine / 30}
              stroke="var(--chart-budget)"
              strokeDasharray="6 4"
              label={{ value: 'Budget', fill: 'var(--chart-budget)', fontSize: 10 }}
            />
          )}
          {viewMode === 'daily' && anomalies.map((d) => (
            <ReferenceDot
              key={d.date}
              x={d.date}
              y={d.cost}
              r={4}
              fill="var(--chart-anomaly)"
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
