/**
 * Cost Anomaly Detector — interactive rolling z-score analysis.
 */

import React, { useState, useMemo, useCallback } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceDot, ResponsiveContainer,
} from 'recharts';
import {
  AlertTriangle, TrendingDown, TrendingUp, SlidersHorizontal,
  ChevronDown, ChevronUp, X,
} from 'lucide-react';
import { useAnomalyData } from '../hooks/useAnomalyData';
import useCostSync from '../hooks/useCostSync';
import AdvancedToolLayout, { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';
import FilterBar from '../components/FilterBar';
import { AdvSkeleton, AdvSyncButton, fmtCurrency } from '../components/advanced/AdvUI';
import { AdvHeroFooter } from '../components/advanced/AdvancedToolHero';

const fmt = (n, currency = 'CAD') => fmtCurrency(n, currency);

const fmtDate = (iso) => {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString('en-CA', { month: 'short', day: 'numeric' });
};

function Skeleton({ className = '' }) {
  return <AdvSkeleton className={className} />;
}

function ChartTooltip({ active, payload, label, anomalyDates, currency, selectedDate }) {
  if (!active || !payload?.length) return null;
  const cost = payload[0]?.value;
  const isAnomaly = anomalyDates.has(label);
  const isSelected = selectedDate === label;
  return (
    <div className="anomaly-chart-tooltip">
      <p className="anomaly-chart-tooltip__date">{fmtDate(label)}</p>
      <p className="anomaly-chart-tooltip__cost">{fmt(cost, currency)}</p>
      {isAnomaly && <p className="anomaly-chart-tooltip__flag">Anomaly detected</p>}
      {isSelected && <p className="anomaly-chart-tooltip__flag" style={{ color: 'var(--primary)' }}>Selected</p>}
    </div>
  );
}

function AnomalyAlert({ anomaly, currency, active, onSelect, onDismiss }) {
  const [expanded, setExpanded] = useState(false);
  const isSpike = anomaly.direction === 'spike';
  const deltaPct = anomaly.baseline_mean
    ? (((anomaly.actual_cost - anomaly.baseline_mean) / anomaly.baseline_mean) * 100).toFixed(1)
    : '—';

  return (
    <div className={`anomaly-alert anomaly-alert--${anomaly.severity}${active ? ' anomaly-alert--active' : ''}`}>
      <div
        className="anomaly-alert__row"
        role="button"
        tabIndex={0}
        onClick={() => onSelect(anomaly.date)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect(anomaly.date);
          }
        }}
      >
        <div className="anomaly-alert__meta">
          {isSpike ? <TrendingUp size={16} className="text-red-500" /> : <TrendingDown size={16} className="text-teal-600" />}
          <span className="anomaly-alert__date">{fmtDate(anomaly.date)}</span>
          <span className={`anomaly-alert__badge anomaly-alert__badge--${anomaly.severity}`}>
            {anomaly.severity}
          </span>
        </div>
        <div className="anomaly-alert__stats">
          <span className="anomaly-alert__cost">{fmt(anomaly.actual_cost, currency)}</span>
          <span className={`anomaly-pct anomaly-pct--${isSpike ? 'spike' : 'drop'}`}>
            {isSpike ? '+' : ''}{deltaPct}%
          </span>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
            className="text-gray-400 hover:text-gray-600"
            aria-label="Toggle detail"
          >
            {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onDismiss(anomaly.date); }}
            className="text-gray-300 hover:text-gray-500"
            aria-label="Dismiss anomaly"
          >
            <X size={14} />
          </button>
        </div>
      </div>
      {expanded && (
        <dl className="anomaly-alert__detail">
          <div><dt>Baseline mean</dt><dd>{fmt(anomaly.baseline_mean, currency)}</dd></div>
          <div><dt>Std deviation</dt><dd>{fmt(anomaly.baseline_stddev, currency)}</dd></div>
          <div><dt>Z-score</dt><dd>{anomaly.z_score.toFixed(2)}σ</dd></div>
        </dl>
      )}
    </div>
  );
}

function ServiceAnomalyTable({ anomalies, currency, selectedDate, onSelectDate, severityFilter, search }) {
  const [sortKey, setSortKey] = useState('z_score');
  const [sortDir, setSortDir] = useState('desc');

  const filtered = useMemo(() => {
    let rows = anomalies ?? [];
    if (severityFilter) rows = rows.filter((a) => a.severity === severityFilter);
    if (selectedDate) rows = rows.filter((a) => a.date === selectedDate);
    const q = (search || '').trim().toLowerCase();
    if (q) rows = rows.filter((a) => (a.service_name || '').toLowerCase().includes(q));
    return rows;
  }, [anomalies, severityFilter, selectedDate, search]);

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    const av = a[sortKey] ?? '';
    const bv = b[sortKey] ?? '';
    if (typeof av === 'number') return sortDir === 'asc' ? av - bv : bv - av;
    return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
  }), [filtered, sortKey, sortDir]);

  function toggleSort(key) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  }

  if (!anomalies?.length) return null;

  return (
    <div className="anomaly-page-card anomaly-service-table">
      <div className="tag-rg-explorer__header">
        <div>
          <h3 className="tag-rg-explorer__title">Per-service anomalies</h3>
          <p className="tag-rg-explorer__sub">
            Services with abnormal spend — click a row to focus the chart on that date
          </p>
        </div>
      </div>
      {!sorted.length ? (
        <div className="tag-rg-explorer__empty">No service anomalies match your filters.</div>
      ) : (
        <div className="tag-rg-explorer__scroll" style={{ maxHeight: '22rem' }}>
          <table className="tag-rg-table">
            <thead>
              <tr>
                {[
                  { key: 'service_name', label: 'Service' },
                  { key: 'date', label: 'Date' },
                  { key: 'actual_cost', label: 'Actual' },
                  { key: 'baseline_mean', label: 'Baseline' },
                  { key: 'z_score', label: 'Z-score' },
                  { key: 'direction', label: 'Direction' },
                  { key: 'severity', label: 'Severity' },
                ].map((col) => (
                  <th
                    key={col.key}
                    className={`tag-rg-table__th--sortable${sortKey === col.key ? ' tag-rg-table__th--active' : ''}`}
                    onClick={() => toggleSort(col.key)}
                  >
                    <span className="tag-rg-table__sort">{col.label}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((a, i) => (
                <tr
                  key={`${a.service_name}-${a.date}-${i}`}
                  className={`tag-rg-table__row${selectedDate === a.date ? ' tag-rg-table__row--active' : ''}`}
                  onClick={() => onSelectDate(a.date)}
                  tabIndex={0}
                  role="button"
                >
                  <td className="tag-rg-table__name" title={a.service_name}>{a.service_name}</td>
                  <td className="tag-rg-table__count">{fmtDate(a.date)}</td>
                  <td className="tag-rg-table__count">{fmt(a.actual_cost, currency)}</td>
                  <td className="tag-rg-table__count">{fmt(a.baseline_mean, currency)}</td>
                  <td className="tag-rg-table__count">{a.z_score.toFixed(2)}σ</td>
                  <td>
                    <span className={`anomaly-pct anomaly-pct--${a.direction === 'spike' ? 'spike' : 'drop'}`}>
                      {a.direction}
                    </span>
                  </td>
                  <td>
                    <span className={`anomaly-alert__badge anomaly-alert__badge--${a.severity}`}>{a.severity}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ControlsPanel({ params, setParams, open, setOpen, loading }) {
  return (
    <div className="anomaly-page-card anomaly-controls">
      <div className="anomaly-controls__head">
        <h2 className="anomaly-controls__title">Detection parameters</h2>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="chip"
        >
          <SlidersHorizontal size={14} />
          {open ? 'Hide parameters' : 'Show parameters'}
        </button>
      </div>
      {open && (
        <div className="anomaly-controls__body">
          {[
            { key: 'window_days', label: 'Baseline window', min: 7, max: 90, step: 1, unit: 'd', help: 'Rolling window for mean and standard deviation.' },
            { key: 'lookback_days', label: 'Inspect window', min: 1, max: 30, step: 1, unit: 'd', help: 'Recent days checked for anomalies.' },
            { key: 'threshold_sigma', label: 'Z-score threshold', min: 1.0, max: 5.0, step: 0.1, unit: 'σ', help: 'Minimum deviation to flag a day.' },
          ].map(({ key, label, min, max, step, unit, help }) => (
            <div key={key} className="anomaly-slider">
              <div className="anomaly-slider__label">
                <span>{label}</span>
                <span className="anomaly-slider__value">{params[key]}{unit}</span>
              </div>
              <input
                type="range"
                min={min}
                max={max}
                step={step}
                value={params[key]}
                disabled={loading}
                onChange={(e) => setParams((p) => ({ ...p, [key]: parseFloat(e.target.value) }))}
              />
              <p className="anomaly-slider__help">{help}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function CostAnomalyDetector() {
  const { subscription } = useAdvancedSubscription();
  const [dismissed, setDismissed] = useState(new Set());
  const [selectedDate, setSelectedDate] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [serviceSearch, setServiceSearch] = useState('');
  const [controlsOpen, setControlsOpen] = useState(false);
  const [params, setParams] = useState({
    window_days: 30,
    lookback_days: 7,
    threshold_sigma: 2.0,
  });

  const { daily, service, loading, error, refetch } = useAnomalyData(subscription, params);
  const { sync, syncing } = useCostSync({ subscription });

  const handleCostSync = useCallback(async () => {
    await sync();
    await refetch();
  }, [sync, refetch]);

  const { chartData, anomalyDates, currency } = useMemo(() => {
    if (!daily?.series?.length) return { chartData: [], anomalyDates: new Set(), currency: daily?.billing_currency ?? 'CAD' };
    const adates = new Set((daily.anomalies ?? []).map((a) => a.date));
    const cur = daily.billing_currency ?? 'CAD';
    const data = daily.series.map((s) => ({
      date: s.date,
      cost: s.cost ?? s.total,
      anomaly: adates.has(s.date) ? (s.cost ?? s.total) : null,
    }));
    return { chartData: data, anomalyDates: adates, currency: cur };
  }, [daily]);

  const visibleAnomalies = useMemo(() => {
    let rows = (daily?.anomalies ?? []).filter((a) => !dismissed.has(a.date));
    if (severityFilter) rows = rows.filter((a) => a.severity === severityFilter);
    if (selectedDate) rows = rows.filter((a) => a.date === selectedDate);
    return rows;
  }, [daily, dismissed, severityFilter, selectedDate]);

  const highCount = (daily?.anomalies ?? []).filter((a) => a.severity === 'high' && !dismissed.has(a.date)).length;
  const medCount = (daily?.anomalies ?? []).filter((a) => a.severity === 'medium' && !dismissed.has(a.date)).length;
  const totalSpend = chartData.reduce((sum, d) => sum + (d.cost ?? 0), 0);

  const toggleSeverity = useCallback((sev) => {
    setSeverityFilter((f) => (f === sev ? '' : sev));
  }, []);

  const toggleDate = useCallback((date) => {
    setSelectedDate((d) => (d === date ? '' : date));
  }, []);

  const hasFilters = !!(severityFilter || selectedDate || serviceSearch.trim());

  return (
    <AdvancedToolLayout
      title="Anomaly detector"
      pageScope="costAnomalyDetector"
      iconKey="anomalyDetector"
      iconRoute="/anomaly-detector"
      accent="anomaly"
      metaItems={[
        `${params.lookback_days}d lookback`,
        `${params.window_days}d baseline window`,
        `Threshold: ${params.threshold_sigma}σ`,
      ]}
      onRefresh={refetch}
      loading={loading || syncing}
      error={error}
      errorTitle="Could not load anomaly data"
      headerActions={(
        <AdvSyncButton
          onClick={handleCostSync}
          syncing={syncing}
          loading={loading}
          label="Sync costs"
        />
      )}
      hero={{
        isLoading: loading && !daily,
        metrics: [
          {
            label: 'Total anomalies',
            value: (daily?.anomaly_count ?? 0).toLocaleString(),
            featured: true,
            tone: (daily?.anomaly_count ?? 0) > 0 ? 'warning' : 'default',
            sub: `${params.lookback_days}d window`,
          },
          {
            label: 'High severity',
            value: highCount.toLocaleString(),
            tone: highCount > 0 ? 'danger' : 'default',
            sub: 'z-score ≥ 3σ',
          },
          {
            label: 'Medium severity',
            value: medCount.toLocaleString(),
            tone: medCount > 0 ? 'warning' : 'default',
            sub: 'z-score ≥ 2σ',
          },
          {
            label: `Total spend (${params.window_days}d)`,
            value: chartData.length ? fmt(totalSpend, currency) : '—',
            sub: `${chartData.length} days charted`,
          },
        ],
        footer: (daily?.anomaly_count ?? 0) > 0 ? (
          <AdvHeroFooter label="Filter by severity — click to focus alerts" icon={AlertTriangle}>
            <div className="adv-hero__severity-row">
              <button type="button" className={`chip${!severityFilter && !selectedDate ? ' active' : ''}`} onClick={() => { setSeverityFilter(''); setSelectedDate(''); }}>
                All {(daily?.anomaly_count ?? 0).toLocaleString()}
              </button>
              <button type="button" className={`chip${severityFilter === 'high' ? ' active' : ''}`} onClick={() => toggleSeverity('high')}>
                High {highCount.toLocaleString()}
              </button>
              <button type="button" className={`chip${severityFilter === 'medium' ? ' active' : ''}`} onClick={() => toggleSeverity('medium')}>
                Medium {medCount.toLocaleString()}
              </button>
            </div>
          </AdvHeroFooter>
        ) : null,
      }}
    >
      <ControlsPanel
        params={params}
        setParams={setParams}
        open={controlsOpen}
        setOpen={setControlsOpen}
        loading={loading}
      />

      {(hasFilters || dismissed.size > 0) && (
        <FilterBar
          className="waste-filter-bar mb-5"
          search={{
            value: serviceSearch,
            onChange: setServiceSearch,
            placeholder: 'Filter service anomalies…',
          }}
          onClear={hasFilters ? () => { setSeverityFilter(''); setSelectedDate(''); setServiceSearch(''); } : undefined}
          resultCount={{
            shown: visibleAnomalies.length,
            total: daily?.anomaly_count ?? 0,
            label: 'alerts',
          }}
        />
      )}

      <div className="anomaly-page-card anomaly-chart-card">
        <div className="anomaly-chart-card__head">
          <div>
            <h2 className="anomaly-chart-card__title">Daily cost — {params.window_days}d baseline</h2>
            <p className="anomaly-chart-card__sub">
              Red dots mark days ≥ {params.threshold_sigma}σ from the rolling mean. Click a point to filter alerts.
            </p>
          </div>
          <div className="anomaly-chart-legend">
            <span className="anomaly-chart-legend__item"><span className="anomaly-chart-legend__line" /> Daily cost</span>
            <span className="anomaly-chart-legend__item"><span className="anomaly-chart-legend__dot" /> Anomaly</span>
          </div>
        </div>

        {loading ? (
          <Skeleton className="h-64 rounded-lg" />
        ) : chartData.length === 0 ? (
          <div className="anomaly-chart-empty">
            <strong>No cost data yet</strong>
            <span>Run a cost sync for this subscription (stores 90 days of daily totals), then refresh.</span>
            {daily?.message && <span>{daily.message}</span>}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart
              data={chartData}
              margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
              onClick={(state) => {
                const date = state?.activeLabel;
                if (date) toggleDate(date);
              }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(156,163,175,0.2)" />
              <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} width={52} />
              <Tooltip content={<ChartTooltip anomalyDates={anomalyDates} currency={currency} selectedDate={selectedDate} />} />
              <Line
                type="monotone"
                dataKey="cost"
                stroke="var(--primary)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5, onClick: (_, p) => toggleDate(p?.payload?.date) }}
              />
              {chartData.filter((d) => anomalyDates.has(d.date)).map((d) => (
                <ReferenceDot
                  key={d.date}
                  x={d.date}
                  y={d.cost}
                  r={selectedDate === d.date ? 7 : 5}
                  fill={selectedDate === d.date ? 'var(--primary)' : '#ef4444'}
                  stroke="#fff"
                  strokeWidth={2}
                  onClick={() => toggleDate(d.date)}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="anomaly-alerts">
        <div className="anomaly-alerts__head">
          <h2 className="anomaly-alerts__title">
            Anomaly alerts
            {visibleAnomalies.length > 0 && (
              <span className="anomaly-alerts__count">{visibleAnomalies.length}</span>
            )}
          </h2>
          {dismissed.size > 0 && (
            <button type="button" className="chip" onClick={() => setDismissed(new Set())}>
              Restore {dismissed.size} dismissed
            </button>
          )}
        </div>

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
          </div>
        ) : visibleAnomalies.length === 0 ? (
          <div className="anomaly-chart-empty">
            <strong>
              {daily?.insufficient_history
                ? 'Not enough history for baseline analysis'
                : daily?.anomaly_count
                  ? 'No alerts match your filters'
                  : 'No anomalies detected'}
            </strong>
            <span>
              {daily?.message
                || (daily?.insufficient_history
                  ? 'Lower the baseline window or run a cost sync to load 90 days of daily spend.'
                  : 'Try widening the baseline window or lowering the z-score threshold.')}
            </span>
          </div>
        ) : (
          <div className="space-y-2">
            {visibleAnomalies.map((a) => (
              <AnomalyAlert
                key={a.date}
                anomaly={a}
                currency={currency}
                active={selectedDate === a.date}
                onSelect={toggleDate}
                onDismiss={(date) => setDismissed((d) => new Set([...d, date]))}
              />
            ))}
          </div>
        )}
      </div>

      {!loading && service?.service_anomalies?.length > 0 && (
        <ServiceAnomalyTable
          anomalies={service.service_anomalies}
          currency={currency}
          selectedDate={selectedDate}
          onSelectDate={toggleDate}
          severityFilter={severityFilter}
          search={serviceSearch}
        />
      )}
      {loading && <Skeleton className="h-48 rounded-xl mt-5" />}
    </AdvancedToolLayout>
  );
}
