import React, { useContext, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeftRight } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import PeriodSelector from '../components/costs/PeriodSelector';
import { fetchCostComparison } from '../api/costs';
import { defaultCompareTimeframe, costTimeframeLabel } from '../config/costTimeframes';
import { formatCurrency } from '../utils/format';
import { QueryErrorState, SubscriptionRequired, LoadingState } from '../components/QueryStates';

function formatPct(value) {
  if (value == null || Number.isNaN(Number(value))) return null;
  return `${Number(value).toFixed(1)}%`;
}

function DeltaBadge({ delta, pct, currency = 'CAD' }) {
  if (delta == null) return null;
  const up = delta > 0;
  const tone = delta === 0 ? 'muted' : up ? 'danger' : 'success';
  const pctLabel = formatPct(pct);
  return (
    <span className={`cost-comparison-delta cost-comparison-delta--${tone}`}>
      {up ? '+' : ''}{formatCurrency(delta, { currency })}
      {pctLabel && ` (${up && pct > 0 ? '+' : ''}${pctLabel})`}
    </span>
  );
}

function ComparisonChart({ services = [], currency }) {
  if (!services.length) {
    return <p className="text-muted">No service breakdown available for these periods.</p>;
  }
  const top = services.slice(0, 8);
  const maxVal = Math.max(...top.map((r) => Math.max(r.current_cost, r.compare_cost)), 1);
  return (
    <div className="cost-comparison-chart" role="img" aria-label="Service cost comparison chart">
      {top.map((row) => (
        <div key={row.service} className="cost-comparison-chart__row">
          <span className="cost-comparison-chart__label" title={row.service}>{row.service}</span>
          <div className="cost-comparison-chart__bars">
            <div
              className="cost-comparison-chart__bar cost-comparison-chart__bar--current"
              style={{ width: `${(row.current_cost / maxVal) * 100}%` }}
              title={`Current: ${formatCurrency(row.current_cost, { currency })}`}
            />
            <div
              className="cost-comparison-chart__bar cost-comparison-chart__bar--compare"
              style={{ width: `${(row.compare_cost / maxVal) * 100}%` }}
              title={`Compare: ${formatCurrency(row.compare_cost, { currency })}`}
            />
          </div>
        </div>
      ))}
      <div className="cost-comparison-chart__legend">
        <span className="cost-comparison-chart__legend-item cost-comparison-chart__legend-item--current">Current</span>
        <span className="cost-comparison-chart__legend-item cost-comparison-chart__legend-item--compare">Compare</span>
      </div>
    </div>
  );
}

export default function CostComparison() {
  const { subscription } = useContext(AppCtx);
  const [currentTimeframe, setCurrentTimeframe] = useState('MonthToDate');
  const [compareTimeframe, setCompareTimeframe] = useState('TheLastMonth');
  const [currentFrom, setCurrentFrom] = useState('');
  const [currentTo, setCurrentTo] = useState('');
  const [compareFrom, setCompareFrom] = useState('');
  const [compareTo, setCompareTo] = useState('');

  const handleCurrentChange = (value) => {
    setCurrentTimeframe(value);
    setCompareTimeframe(defaultCompareTimeframe(value));
  };

  const queryKey = useMemo(() => ([
    'cost-comparison',
    subscription,
    currentTimeframe,
    compareTimeframe,
    currentFrom,
    currentTo,
    compareFrom,
    compareTo,
  ]), [subscription, currentTimeframe, compareTimeframe, currentFrom, currentTo, compareFrom, compareTo]);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey,
    queryFn: () => fetchCostComparison({
      subscription_id: subscription,
      current_timeframe: currentTimeframe,
      compare_timeframe: compareTimeframe,
      current_from_date: currentFrom || undefined,
      current_to_date: currentTo || undefined,
      compare_from_date: compareFrom || undefined,
      compare_to_date: compareTo || undefined,
    }),
    enabled: !!subscription,
    staleTime: 5 * 60_000,
  });

  const currency = data?.currency || 'CAD';

  return (
    <div className="page cost-comparison-page">
      <PageHeader
        title="Cost comparison"
        subtitle="Compare spend across two periods side by side."
        icon={ArrowLeftRight}
      />

      {!subscription && <SubscriptionRequired />}

      {subscription && (
        <>
          <PeriodSelector
            currentTimeframe={currentTimeframe}
            compareTimeframe={compareTimeframe}
            onCurrentChange={handleCurrentChange}
            onCompareChange={setCompareTimeframe}
            currentFromDate={currentFrom}
            currentToDate={currentTo}
            onCurrentFromChange={setCurrentFrom}
            onCurrentToChange={setCurrentTo}
            compareFromDate={compareFrom}
            compareToDate={compareTo}
            onCompareFromChange={setCompareFrom}
            onCompareToChange={setCompareTo}
          />

          {isLoading && <LoadingState message="Loading comparison…" />}
          {isError && <QueryErrorState error={error} onRetry={refetch} />}

          {data && !isLoading && (
            <>
              <div className="cost-comparison-summary card">
                <div className="cost-comparison-summary__col">
                  <p className="cost-comparison-summary__label">{costTimeframeLabel(currentTimeframe)}</p>
                  <p className="cost-comparison-summary__value">{formatCurrency(data.current_total, { currency })}</p>
                </div>
                <div className="cost-comparison-summary__col">
                  <p className="cost-comparison-summary__label">{costTimeframeLabel(compareTimeframe)}</p>
                  <p className="cost-comparison-summary__value">{formatCurrency(data.compare_total, { currency })}</p>
                </div>
                <div className="cost-comparison-summary__col">
                  <p className="cost-comparison-summary__label">Change</p>
                  <DeltaBadge delta={data.delta} pct={data.pct_change} currency={currency} />
                </div>
              </div>

              <ComparisonChart services={data.services} currency={currency} />

              <div className="card cost-comparison-table-wrap">
                <table className="data-table cost-comparison-table">
                  <thead>
                    <tr>
                      <th scope="col">Service</th>
                      <th scope="col">Current</th>
                      <th scope="col">Compare</th>
                      <th scope="col">Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.services || []).slice(0, 25).map((row) => (
                      <tr key={row.service}>
                        <td>{row.service}</td>
                        <td>{formatCurrency(row.current_cost, { currency })}</td>
                        <td>{formatCurrency(row.compare_cost, { currency })}</td>
                        <td>
                          <DeltaBadge delta={row.delta} pct={row.pct_change} currency={currency} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
