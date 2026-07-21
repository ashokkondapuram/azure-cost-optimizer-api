/**
 * Waste Heatmap page
 *
 * Visualises idle/orphaned resource waste as a category × severity heatmap,
 * Recharts breakdowns, and a sortable findings table with the full resource insight drawer.
 *
 * Data: GET /idle-resources/sweep/{subscriptionId}
 *       GET /idle-resources/summary/{subscriptionId}
 */

import React, { useState, useMemo, useCallback, useEffect, useRef, useContext } from 'react';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts';
import { ChevronUp, ChevronDown, X, Flame } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { AppCtx } from '../App';
import { fetchIdleSweep, fetchIdleSummary } from '../api/wasteHeatmap';
import WasteHeatmapHero, { WasteHeatmapDataNote } from '../components/waste/WasteHeatmapHero';
import ResourceInsightDrawer from '../components/ResourceInsightDrawer';
import useFindingsIndex from '../hooks/useFindingsIndex';
import { resolveResourceFindings } from '../utils/resourceFindingsUtils';
import { normalizeArmId } from '../utils/findingDedupe';
import { wasteHeatmapFiltersFromSearchParams } from '../utils/wasteHeatmapLinks';
import FilterBar from '../components/FilterBar';
import PaginationControls from '../components/table/PaginationControls';
import { AdvEmptyState, AdvSkeleton } from '../components/advanced/AdvUI';
import { SubscriptionRequired, QueryErrorState } from '../components/QueryStates';
import { formatCurrency } from '../utils/format';
import { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';
import {
  SEVERITY_COLORS, CHART_PALETTE, CHART_AXIS_TICK, CHART_GRID,
} from '../components/wiz/charts/wizChartColors';

// ── constants & helpers ─────────────────────────────────────────────────────
const CATEGORY_COLORS = CHART_PALETTE;

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'];
const SEVERITY_LABEL = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low', info: 'Info' };
const SEVERITY_COLOR = {
  critical: SEVERITY_COLORS.CRITICAL,
  high: SEVERITY_COLORS.HIGH,
  medium: SEVERITY_COLORS.MEDIUM,
  low: SEVERITY_COLORS.LOW,
  info: SEVERITY_COLORS.INFO,
};

function fmtMoney(n, currency = 'CAD') {
  return formatCurrency(n, { currency, decimals: 0 });
}

function fmtSavings(amount, currency = 'CAD') {
  const value = Number(amount);
  if (!value || Number.isNaN(value) || value <= 0) return null;
  return fmtMoney(value, currency);
}

const CATEGORY_ORDER = ['Compute', 'Kubernetes', 'Storage', 'Network', 'Database', 'Security', 'Cost', 'Other'];

const EMPTY_FILTERS = { severity: null, category: null, ruleId: null, search: '' };
const API_PATH = '/resources/from-cost';

function findingToResourceRow(item) {
  if (!item?.resource_id) return null;
  return {
    id: item.resource_id,
    resource_id: item.resource_id,
    name: item.resource_name,
    resourceGroup: item.resource_group,
    resource_group: item.resource_group,
    location: item.location,
    type: item.resource_type,
    azureServiceName: item.resource_type,
  };
}

function findingFallbackForDrawer(item) {
  if (!item) return [];
  return [{
    id: item.finding_id,
    rule_id: item.rule_id,
    rule_name: item.title,
    severity: String(item.severity || 'medium').toUpperCase(),
    detail: item.detail,
    recommendation: item.recommendation,
    estimated_savings_usd: item.estimated_savings_usd ?? 0,
    resource_id: item.resource_id,
  }];
}

function normalizeSeverity(value) {
  const sev = String(value || 'medium').toLowerCase();
  return SEVERITIES.includes(sev) ? sev : 'low';
}

function sortCategories(categories) {
  return [...categories].sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a);
    const bi = CATEGORY_ORDER.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
}

function applyWasteFilters(items, filters) {
  if (!items?.length) return [];
  const q = filters.search.trim().toLowerCase();
  return items.filter((item) => {
    if (filters.severity && normalizeSeverity(item.severity) !== filters.severity) return false;
    if (filters.category && (item.category || 'Other') !== filters.category) return false;
    if (filters.ruleId && item.rule_id !== filters.ruleId) return false;
    if (!q) return true;
    const hay = [
      item.resource_name,
      item.resource_id,
      item.category,
      item.title,
      item.rule_id,
      item.detail,
    ].filter(Boolean).join(' ').toLowerCase();
    return hay.includes(q);
  });
}

function Skeleton({ className = '' }) {
  return <AdvSkeleton className={className} />;
}

function ChartTooltip({ active, payload, label, currency = 'CAD' }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  return (
    <div className="waste-chart-tooltip">
      <p className="waste-chart-tooltip__title">{label || row?.name}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="waste-chart-tooltip__row">
          {p.name}: <strong>{typeof p.value === 'number' && p.dataKey?.includes('savings') ? fmtMoney(p.value, currency) : p.value}</strong>
        </p>
      ))}
    </div>
  );
}

function buildGridFromMatrix(heatmapMatrix) {
  const grid = {};
  let maxSavings = 0;
  let maxCount = 0;
  const categories = new Set();
  for (const [key, cell] of Object.entries(heatmapMatrix || {})) {
    const count = cell?.count ?? 0;
    const savings = cell?.savings_usd ?? cell?.savings ?? 0;
    if (!count) continue;
    grid[key] = { count, savings };
    categories.add(key.split('|')[0]);
    if (savings > maxSavings) maxSavings = savings;
    if (count > maxCount) maxCount = count;
  }
  return {
    categories: sortCategories([...categories]),
    grid,
    maxSavings,
    maxCount,
  };
}

// ── Recharts: severity donut ────────────────────────────────────────────────
function SeverityDonutChart({ bySeverity, loading, activeSeverity, onSelectSeverity }) {
  const data = useMemo(() => (
    SEVERITIES.map((key) => ({
      key,
      name: SEVERITY_LABEL[key],
      value: bySeverity?.[key] ?? 0,
    })).filter((d) => d.value > 0)
  ), [bySeverity]);

  if (loading) return <Skeleton className="h-56 rounded-xl" />;
  if (!data.length) return null;

  return (
    <div className="waste-chart-card wiz-card">
      <h3 className="waste-chart-card__title">Findings by severity</h3>
      <p className="waste-chart-card__sub">Click a slice or legend chip to filter the table</p>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={52}
            outerRadius={82}
            dataKey="value"
            nameKey="name"
            paddingAngle={2}
            onClick={(_, index) => onSelectSeverity(data[index]?.key)}
          >
            {data.map((entry) => (
              <Cell
                key={entry.key}
                fill={SEVERITY_COLOR[entry.key]}
                stroke={activeSeverity === entry.key ? 'var(--text)' : 'transparent'}
                strokeWidth={activeSeverity === entry.key ? 2 : 0}
                opacity={activeSeverity && activeSeverity !== entry.key ? 0.45 : 1}
                style={{ cursor: 'pointer' }}
              />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      <div className="waste-chart-legend">
        {data.map((d) => (
          <button
            key={d.key}
            type="button"
            className={`chip${activeSeverity === d.key ? ' active' : ''}`}
            onClick={() => onSelectSeverity(d.key)}
          >
            <span className="waste-chart-legend__dot" style={{ background: SEVERITY_COLOR[d.key] }} />
            {d.name} ({d.value})
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Recharts: category savings bars ───────────────────────────────────────
function CategorySavingsChart({
  byCategory, byCategorySavings, loading, activeCategory, onSelectCategory, currency = 'CAD',
}) {
  const data = useMemo(() => {
    if (!byCategory) return [];
    return sortCategories(Object.keys(byCategory))
      .map((name) => ({
        name,
        count: byCategory[name] ?? 0,
        savings: byCategorySavings?.[name] ?? 0,
      }))
      .sort((a, b) => (b.savings || b.count) - (a.savings || a.count))
      .slice(0, 8);
  }, [byCategory, byCategorySavings]);

  const savingsMode = data.some((row) => row.savings > 0);

  if (loading) return <Skeleton className="h-56 rounded-xl" />;
  if (!data.length) return null;

  return (
    <div className="waste-chart-card wiz-card">
      <h3 className="waste-chart-card__title">{savingsMode ? 'Savings by category' : 'Findings by category'}</h3>
      <p className="waste-chart-card__sub">Click a bar to filter findings in that category</p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 12, bottom: 0, left: 4 }}
          onClick={(state) => {
            const name = state?.activePayload?.[0]?.payload?.name;
            if (name) onSelectCategory(name);
          }}
        >
          <CartesianGrid {...CHART_GRID} horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={(v) => (savingsMode ? `$${(v / 1000).toFixed(0)}k` : v.toLocaleString())}
            tick={CHART_AXIS_TICK}
          />
          <YAxis type="category" dataKey="name" width={88} tick={CHART_AXIS_TICK} />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload;
              return (
                <div className="waste-chart-tooltip">
                  <p className="waste-chart-tooltip__title">{row.name}</p>
                  <p className="waste-chart-tooltip__row">Findings: <strong>{row.count}</strong></p>
                  {savingsMode && (
                    <p className="waste-chart-tooltip__row">Est. savings: <strong>{fmtMoney(row.savings, currency)}</strong></p>
                  )}
                </div>
              );
            }}
          />
          <Bar
            dataKey={savingsMode ? 'savings' : 'count'}
            name={savingsMode ? 'Est. savings' : 'Findings'}
            radius={[0, 4, 4, 0]}
            cursor="pointer"
          >
            {data.map((entry, index) => (
              <Cell
                key={entry.name}
                fill={activeCategory === entry.name ? '#c2410c' : CATEGORY_COLORS[index % CATEGORY_COLORS.length]}
                opacity={activeCategory && activeCategory !== entry.name ? 0.45 : 0.92}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Interactive heatmap grid ────────────────────────────────────────────────
function HeatmapGrid({
  heatmapMatrix,
  loading,
  activeCategory,
  activeSeverity,
  hoveredCell,
  onHoverCell,
  onCellClick,
  onCategoryClick,
  onSeverityClick,
}) {
  const { categories, grid, maxSavings, maxCount } = useMemo(
    () => buildGridFromMatrix(heatmapMatrix),
    [heatmapMatrix],
  );
  const useCountIntensity = maxSavings <= 0 && maxCount > 0;

  if (loading) return <Skeleton className="h-52 rounded-xl" />;
  if (!categories.length) {
    return (
      <div className="heatmap-empty">
        <strong>No heatmap data yet</strong>
        <span>Run optimization analysis to populate idle and waste findings.</span>
      </div>
    );
  }

  const hoverKey = hoveredCell ? `${hoveredCell.category}|${hoveredCell.severity}` : null;

  return (
    <div className="heatmap-wrap">
      <table className="heatmap-table">
        <thead>
          <tr>
            <th className="heatmap-th-label">Category</th>
            {SEVERITIES.map((s) => (
              <th
                key={s}
                className={`heatmap-th heatmap-th--${s} heatmap-th--clickable${activeSeverity === s ? ' heatmap-th--active' : ''}`}
                onClick={() => onSeverityClick(s)}
                title={`Filter by ${SEVERITY_LABEL[s]}`}
              >
                {SEVERITY_LABEL[s]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((cat) => (
            <tr key={cat}>
              <td
                className={`heatmap-row-label heatmap-row-label--clickable${activeCategory === cat ? ' heatmap-row-label--active' : ''}`}
                onClick={() => onCategoryClick(cat)}
                title={`Filter by ${cat}`}
              >
                {cat}
              </td>
              {SEVERITIES.map((sev) => {
                const key = `${cat}|${sev}`;
                const cell = grid[key];
                const intensity = cell
                  ? (useCountIntensity
                    ? Math.max(0.12, cell.count / maxCount)
                    : Math.max(0.12, cell.savings / maxSavings))
                  : 0;
                const isActive = activeCategory === cat && activeSeverity === sev;
                const isHovered = hoverKey === key;
                return (
                  <td key={sev}>
                    <button
                      type="button"
                      title={cell
                        ? `${cell.count} finding${cell.count !== 1 ? 's' : ''}${fmtSavings(cell.savings) ? ` · ${fmtSavings(cell.savings)}` : ''}`
                        : 'No findings'}
                      className={[
                        'heatmap-cell',
                        `heatmap-cell--${sev}`,
                        cell ? 'heatmap-cell--has-data' : 'heatmap-cell--empty',
                        isActive ? 'heatmap-cell--active' : '',
                        isHovered ? 'heatmap-cell--hovered' : '',
                      ].filter(Boolean).join(' ')}
                      style={{ '--intensity': intensity }}
                      onMouseEnter={() => onHoverCell({ category: cat, severity: sev, ...cell })}
                      onMouseLeave={() => onHoverCell(null)}
                      onClick={() => onCellClick(cat, sev)}
                      disabled={!cell}
                    >
                      {cell ? (
                        <>
                          <span className="heatmap-cell__val">{cell.count}</span>
                          {fmtSavings(cell.savings) ? (
                            <span className="heatmap-cell__val heatmap-cell__savings">{fmtSavings(cell.savings)}</span>
                          ) : (
                            <span className="heatmap-cell__val heatmap-cell__savings heatmap-cell__savings--muted">No est.</span>
                          )}
                        </>
                      ) : (
                        <span className="heatmap-cell__val heatmap-cell__empty">—</span>
                      )}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {hoveredCell?.count > 0 && (
        <div className="heatmap-tooltip" role="status">
          <strong>{hoveredCell.category}</strong>
          <span>·</span>
          <span>{SEVERITY_LABEL[hoveredCell.severity]}</span>
          <span>·</span>
          <span>{hoveredCell.count} finding{hoveredCell.count !== 1 ? 's' : ''}</span>
          {fmtSavings(hoveredCell.savings) && (
            <>
              <span>·</span>
              <span>{fmtSavings(hoveredCell.savings)}</span>
            </>
          )}
        </div>
      )}

      <div className="heatmap-legend">
        <span className="heatmap-legend__label">{useCountIntensity ? 'Finding density' : 'Savings intensity'}</span>
        <span className="heatmap-legend__scale" aria-hidden="true" />
        <span>Low</span>
        <span>High</span>
      </div>
    </div>
  );
}

// ── Top rules (Recharts) ────────────────────────────────────────────────────
function TopRulesChart({ rules, loading, activeRuleId, onSelectRule, currency = 'CAD' }) {
  const top = useMemo(() => (rules ?? []).slice(0, 8), [rules]);
  const savingsMode = top.some((row) => (row.savings_usd ?? 0) > 0);
  const chartData = useMemo(
    () => [...top].sort((a, b) => (
      savingsMode
        ? (b.savings_usd ?? 0) - (a.savings_usd ?? 0)
        : (b.count ?? 0) - (a.count ?? 0)
    )),
    [top, savingsMode],
  );

  if (loading) return <Skeleton className="h-48 rounded-xl" />;
  if (!chartData.length) return null;

  return (
    <div className="waste-chart-card wiz-card">
      <h3 className="waste-chart-card__title">
        {savingsMode ? 'Top waste rules by savings' : 'Top waste rules by volume'}
      </h3>
      <p className="waste-chart-card__sub">Click a bar to filter findings by rule</p>
      <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 36)}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 12, bottom: 0, left: 4 }}
          onClick={(state) => {
            const ruleId = state?.activePayload?.[0]?.payload?.rule_id;
            if (ruleId) onSelectRule(ruleId);
          }}
        >
          <CartesianGrid {...CHART_GRID} horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={(v) => (savingsMode ? `$${(v / 1000).toFixed(0)}k` : v.toLocaleString())}
            tick={CHART_AXIS_TICK}
          />
          <YAxis
            type="category"
            dataKey="title"
            width={140}
            tick={CHART_AXIS_TICK}
            tickFormatter={(v, i) => {
              const label = chartData[i]?.title ?? chartData[i]?.rule_id ?? v;
              return label.length > 22 ? `${label.slice(0, 20)}…` : label;
            }}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload;
              return (
                <div className="waste-chart-tooltip">
                  <p className="waste-chart-tooltip__title">{row.title ?? row.rule_id}</p>
                  <p className="waste-chart-tooltip__row">Findings: <strong>{row.count}</strong></p>
                  {savingsMode && (
                    <p className="waste-chart-tooltip__row">Est. savings: <strong>{fmtMoney(row.savings_usd, currency)}</strong></p>
                  )}
                </div>
              );
            }}
          />
          <Bar
            dataKey={savingsMode ? 'savings_usd' : 'count'}
            name={savingsMode ? 'Est. savings' : 'Findings'}
            radius={[0, 4, 4, 0]}
            cursor="pointer"
          >
            {chartData.map((entry, index) => (
              <Cell
                key={entry.rule_id}
                fill={activeRuleId === entry.rule_id ? '#c2410c' : CATEGORY_COLORS[index % CATEGORY_COLORS.length]}
                opacity={activeRuleId && activeRuleId !== entry.rule_id ? 0.45 : 0.92}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Findings table ──────────────────────────────────────────────────────────
const COLS = [
  { key: 'resource_name', label: 'Resource' },
  { key: 'category', label: 'Category' },
  { key: 'severity', label: 'Severity' },
  { key: 'title', label: 'Finding' },
  { key: 'estimated_savings_usd', label: 'Est. savings' },
];

function FindingsTable({ items, allCount, loading, onSelectRow, selectedFindingId, tableRef }) {
  const [sortKey, setSortKey] = useState('estimated_savings_usd');
  const [sortDir, setSortDir] = useState('desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const sorted = useMemo(() => {
    if (!items?.length) return [];
    return [...items].sort((a, b) => {
      const av = a[sortKey] ?? '';
      const bv = b[sortKey] ?? '';
      if (typeof av === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [items, sortKey, sortDir]);

  const pageItems = sorted.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => {
    setPage(1);
  }, [items, sortKey, sortDir, pageSize]);

  function toggleSort(key) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
    setPage(1);
  }

  if (loading) return <Skeleton className="h-48 rounded-xl" />;

  return (
    <div ref={tableRef} className="wiz-card waste-findings-table">
      <div className="tag-rg-explorer__header">
        <div>
          <h3 className="tag-rg-explorer__title">Idle resource findings</h3>
          <p className="tag-rg-explorer__sub">
            {sorted.length.toLocaleString()} showing
            {allCount !== sorted.length ? ` of ${allCount.toLocaleString()}` : ''}
            {' · '}Click a row to open the full resource insight drawer
          </p>
        </div>
      </div>

      {!sorted.length ? (
        <div className="heatmap-empty heatmap-empty--compact">
          <strong>No findings match your filters</strong>
          <span>Clear filters or broaden your search to see more rows.</span>
        </div>
      ) : (
        <div className="tag-rg-explorer__scroll">
          <table className="tag-rg-table">
            <thead>
              <tr>
                {COLS.map((c) => (
                  <th
                    key={c.key}
                    className={`tag-rg-table__th--sortable${sortKey === c.key ? ' tag-rg-table__th--active' : ''}`}
                    onClick={() => toggleSort(c.key)}
                  >
                    <span className="tag-rg-table__sort">
                      {c.label}
                      {sortKey === c.key && (sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageItems.map((item, i) => (
                <tr
                  key={item.finding_id ?? i}
                  className={[
                    'tag-rg-table__row',
                    'waste-findings-table__row',
                    selectedFindingId === item.finding_id ? 'waste-findings-table__row--selected' : '',
                  ].filter(Boolean).join(' ')}
                  tabIndex={0}
                  role="button"
                  onClick={() => onSelectRow(item)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelectRow(item);
                    }
                  }}
                >
                  <td className="tag-rg-table__name" title={item.resource_name}>
                    {item.resource_name || item.resource_id || '—'}
                  </td>
                  <td className="tag-rg-table__mono">{item.category}</td>
                  <td>
                    <span className={`waste-severity-pill waste-severity-pill--${normalizeSeverity(item.severity)}`}>
                      {SEVERITY_LABEL[normalizeSeverity(item.severity)] || item.severity}
                    </span>
                  </td>
                  <td className="tag-rg-table__mono" title={item.title}>{item.title}</td>
                  <td className="tag-rg-table__count wiz-savings-cell--positive">
                    {fmtSavings(item.estimated_savings_usd) ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {sorted.length > 0 && (
        <PaginationControls
          page={page}
          pageSize={pageSize}
          total={sorted.length}
          onPageChange={setPage}
          onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
          pageSizeOptions={[20, 50, 100]}
        />
      )}
    </div>
  );
}

function ActiveFilterChips({ filters, onClearSeverity, onClearCategory, onClearRule }) {
  const chips = [];
  if (filters.severity) {
    chips.push({ key: 'severity', label: SEVERITY_LABEL[filters.severity], onClear: onClearSeverity });
  }
  if (filters.category) {
    chips.push({ key: 'category', label: filters.category, onClear: onClearCategory });
  }
  if (filters.ruleId) {
    chips.push({ key: 'rule', label: filters.ruleId, onClear: onClearRule });
  }
  if (!chips.length) return null;

  return (
    <div className="toolbar waste-filter-chips">
      <span className="toolbar__label">Active filters</span>
      {chips.map((chip) => (
        <button key={chip.key} type="button" className="chip active" onClick={chip.onClear}>
          {chip.label}
          <X size={12} aria-hidden />
        </button>
      ))}
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function WasteHeatmap() {
  const { subscription: ctxSubscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const { subscription, subscriptionLabel } = useAdvancedSubscription();
  const activeSubscription = subscription || ctxSubscription;
  const { byResourceId, indexReady } = useFindingsIndex(activeSubscription);
  const [searchParams] = useSearchParams();
  const [sweep, setSweep] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [hoveredCell, setHoveredCell] = useState(null);
  const [selectedFinding, setSelectedFinding] = useState(null);
  const tableRef = useRef(null);

  const load = useCallback(async () => {
    if (!subscription?.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const [sw, sm] = await Promise.all([fetchIdleSweep(subscription), fetchIdleSummary(subscription)]);
      setSweep(sw);
      setSummary(sm);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [subscription]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setFilters(EMPTY_FILTERS);
    setSelectedFinding(null);
  }, [subscription]);

  useEffect(() => {
    const fromUrl = wasteHeatmapFiltersFromSearchParams(searchParams);
    if (!fromUrl.category && !fromUrl.severity && !fromUrl.ruleId) return;
    setFilters((current) => ({
      ...current,
      category: fromUrl.category || null,
      severity: fromUrl.severity || null,
      ruleId: fromUrl.ruleId || null,
    }));
  }, [searchParams, subscription]);

  const allItems = sweep?.idle_resources ?? [];
  const filteredItems = useMemo(() => applyWasteFilters(allItems, filters), [allItems, filters]);
  const hasFilters = !!(filters.severity || filters.category || filters.ruleId || filters.search.trim());

  const scrollToTable = useCallback(() => {
    tableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const toggleSeverity = useCallback((severity) => {
    setFilters((f) => ({
      ...f,
      severity: f.severity === severity ? null : severity,
      ruleId: null,
    }));
    scrollToTable();
  }, [scrollToTable]);

  const toggleCategory = useCallback((category) => {
    setFilters((f) => ({
      ...f,
      category: f.category === category ? null : category,
      ruleId: null,
    }));
    scrollToTable();
  }, [scrollToTable]);

  const toggleCell = useCallback((category, severity) => {
    setFilters((f) => {
      const same = f.category === category && f.severity === severity;
      if (same) return { ...f, category: null, severity: null };
      return { ...f, category, severity, ruleId: null };
    });
    scrollToTable();
  }, [scrollToTable]);

  const toggleRule = useCallback((ruleId) => {
    setFilters((f) => ({
      ...f,
      ruleId: f.ruleId === ruleId ? null : ruleId,
    }));
    scrollToTable();
  }, [scrollToTable]);

  const clearFilters = useCallback(() => setFilters(EMPTY_FILTERS), []);

  const handleSelectRow = useCallback((item) => {
    setSelectedFinding((current) => (
      current?.finding_id === item.finding_id ? null : item
    ));
  }, []);

  const drawerResource = useMemo(
    () => (selectedFinding ? findingToResourceRow(selectedFinding) : null),
    [selectedFinding],
  );

  const drawerFindings = useMemo(() => {
    if (!drawerResource || !selectedFinding) return [];
    const rid = normalizeArmId(drawerResource.id);
    return resolveResourceFindings(
      drawerResource,
      byResourceId.get(rid) || findingFallbackForDrawer(selectedFinding),
      { indexReady, apiPath: API_PATH },
    );
  }, [drawerResource, selectedFinding, byResourceId, indexReady]);

  const categoryOptions = useMemo(() => (
    sortCategories(Object.keys(sweep?.by_category ?? {}))
      .map((c) => ({ value: c, label: c }))
  ), [sweep?.by_category]);

  const isEmpty = !loading && !error && sweep && (sweep.total_idle_findings ?? 0) === 0;

  if (!activeSubscription) {
    return (
      <div className="page-shell wiz-page waste-heatmap-page">
        <SubscriptionRequired />
      </div>
    );
  }

  return (
    <div className="page-shell wiz-page waste-heatmap-page">
      {error && (
        <QueryErrorState
          error={error}
          title="Could not load waste heatmap"
          onRetry={load}
        />
      )}

      <div className="wiz-panel waste-heatmap-panel">
      <WasteHeatmapHero
        sweep={sweep}
        loading={loading}
        activeSeverity={filters.severity}
        activeCategory={filters.category}
        onSeverityClick={toggleSeverity}
        onCategoryClick={toggleCategory}
        subscriptionLabel={subscriptionLabel}
        onRefresh={load}
        refreshDisabled={loading}
      />

      <WasteHeatmapDataNote sweep={sweep} summary={summary} />

      {isEmpty && (
        <AdvEmptyState
          title="No idle findings yet"
          description="Run optimization analysis to detect idle disks, orphaned resources, Redis and PostgreSQL waste, and other patterns."
          icon={Flame}
          action={(
            <Link to="/action-centre?hasAction=1" className="btn btn-primary btn-sm">
              Proposed actions
            </Link>
          )}
        />
      )}

      <FilterBar
        className="waste-filter-bar"
        search={{
          value: filters.search,
          onChange: (search) => setFilters((f) => ({ ...f, search })),
          placeholder: 'Search resources, findings, or rules…',
        }}
        selects={[
          {
            id: 'severity',
            label: 'Severity',
            value: filters.severity || '',
            onChange: (v) => setFilters((f) => ({ ...f, severity: v || null, ruleId: null })),
            options: [
              { value: '', label: 'All severities' },
              ...SEVERITIES.map((s) => ({ value: s, label: SEVERITY_LABEL[s] })),
            ],
          },
          {
            id: 'category',
            label: 'Category',
            value: filters.category || '',
            onChange: (v) => setFilters((f) => ({ ...f, category: v || null, ruleId: null })),
            options: [
              { value: '', label: 'All categories' },
              ...categoryOptions,
            ],
          },
        ]}
        onClear={hasFilters ? clearFilters : undefined}
        resultCount={{
          shown: filteredItems.length,
          total: allItems.length,
          label: 'findings',
        }}
      />

      <ActiveFilterChips
        filters={filters}
        onClearSeverity={() => setFilters((f) => ({ ...f, severity: null }))}
        onClearCategory={() => setFilters((f) => ({ ...f, category: null }))}
        onClearRule={() => setFilters((f) => ({ ...f, ruleId: null }))}
      />

      {!isEmpty && (
        <>
      <div className="wiz-chart-grid waste-charts-grid mb-5">
        <SeverityDonutChart
          bySeverity={sweep?.by_severity}
          loading={loading}
          activeSeverity={filters.severity}
          onSelectSeverity={toggleSeverity}
        />
        <CategorySavingsChart
          byCategory={sweep?.by_category}
          byCategorySavings={sweep?.by_category_savings}
          loading={loading}
          activeCategory={filters.category}
          onSelectCategory={toggleCategory}
          currency={currency}
        />
      </div>

      <section className="waste-section-card wiz-card mb-5" aria-labelledby="waste-heatmap-title">
        <div className="waste-section-card__head">
          <div>
            <h2 id="waste-heatmap-title" className="waste-section-card__title">Category × severity heatmap</h2>
            <p className="waste-section-card__sub">
              {(sweep?.total_idle_findings ?? 0).toLocaleString()} findings across the subscription.
              Click a cell, row, or column to filter the table.
              {(sweep?.total_estimated_savings_usd ?? 0) <= 0
                ? ' Color reflects finding count when savings are not estimated.'
                : ' Color reflects estimated savings intensity.'}
            </p>
          </div>
        </div>
        <HeatmapGrid
          heatmapMatrix={sweep?.heatmap_matrix}
          loading={loading}
          activeCategory={filters.category}
          activeSeverity={filters.severity}
          hoveredCell={hoveredCell}
          onHoverCell={setHoveredCell}
          onCellClick={toggleCell}
          onCategoryClick={toggleCategory}
          onSeverityClick={toggleSeverity}
        />
      </section>

      {(summary?.top_rules?.length > 0 || loading) && (
        <div className="mb-5">
          <TopRulesChart
            rules={summary?.top_rules}
            loading={loading}
            currency={currency}
            activeRuleId={filters.ruleId}
            onSelectRule={toggleRule}
          />
        </div>
      )}

      <FindingsTable
        items={filteredItems}
        allCount={sweep?.total_idle_findings ?? allItems.length}
        loading={loading}
        onSelectRow={handleSelectRow}
        selectedFindingId={selectedFinding?.finding_id}
        tableRef={tableRef}
      />

      {drawerResource && (
        <ResourceInsightDrawer
          resource={drawerResource}
          apiPath={API_PATH}
          findings={drawerFindings}
          indexReady={indexReady}
          currency={currency}
          onClose={() => setSelectedFinding(null)}
        />
      )}
        </>
      )}
      </div>
    </div>
  );
}

// Exported for unit tests
export { applyWasteFilters, normalizeSeverity, sortCategories };
