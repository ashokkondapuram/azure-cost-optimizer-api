/**
 * Tag Compliance Scorecard page
 *
 * Data: GET /tag-compliance/score/{subscriptionId}
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts';
import { ChevronUp, ChevronDown, X } from 'lucide-react';
import { fetchComplianceScore } from '../api/tagCompliance';
import AdvancedToolLayout, { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';
import { AdvSkeleton } from '../components/advanced/AdvUI';
import TagComplianceHero, { TagComplianceDataNote } from '../components/tag/TagComplianceHero';
import FilterBar from '../components/FilterBar';
import ResourceInsightDrawer from '../components/ResourceInsightDrawer';
import PaginationControls from '../components/table/PaginationControls';

const DEFAULT_TAGS = ['environment', 'owner', 'cost-center'];
const EMPTY_FILTERS = { search: '', resourceGroup: '', resourceType: '', missingTag: '' };
const CHART_COLORS = ['#0d9488', '#ef4444', '#0891b2', '#7c3aed', '#f97316', '#16a34a', '#db2777', '#ea580c'];

function scoreColour(pct) {
  if (pct == null) return { text: 'text-gray-500', fill: '#9ca3af' };
  if (pct >= 90) return { text: 'text-teal-600 dark:text-teal-400', fill: '#0d9488' };
  if (pct >= 70) return { text: 'text-amber-600 dark:text-amber-400', fill: '#f59e0b' };
  return { text: 'text-red-600 dark:text-red-400', fill: '#ef4444' };
}

function Skeleton({ className = '' }) {
  return <AdvSkeleton className={className} />;
}

function applyTagFilters(items, filters) {
  if (!items?.length) return [];
  const q = filters.search.trim().toLowerCase();
  return items.filter((row) => {
    if (filters.resourceGroup && (row.resource_group || '').toLowerCase() !== filters.resourceGroup.toLowerCase()) {
      return false;
    }
    if (filters.resourceType && !(row.resource_type || '').toLowerCase().includes(filters.resourceType.toLowerCase())) {
      return false;
    }
    if (filters.missingTag && !(row.missing_tags || []).includes(filters.missingTag)) {
      return false;
    }
    if (!q) return true;
    const hay = [row.resource_name, row.resource_type, row.resource_group, ...(row.missing_tags || [])]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return hay.includes(q);
  });
}

function ComplianceDonut({ data, loading, onSelectSlice, activeSlice }) {
  const chartData = useMemo(() => {
    if (!data?.total_resources) return [];
    return [
      { key: 'compliant', name: 'Fully compliant', value: data.fully_compliant ?? 0 },
      { key: 'non-compliant', name: 'Non-compliant', value: data.non_compliant_count ?? 0 },
    ].filter((row) => row.value > 0);
  }, [data]);

  if (loading) return <Skeleton className="h-56 rounded-xl" />;
  if (!chartData.length) return null;

  const colors = { compliant: '#0d9488', 'non-compliant': '#ef4444' };

  return (
    <div className="waste-chart-card">
      <h3 className="waste-chart-card__title">Compliance split</h3>
      <p className="waste-chart-card__sub">Click a slice to filter the table</p>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={52}
            outerRadius={82}
            dataKey="value"
            nameKey="name"
            paddingAngle={2}
            onClick={(_, index) => onSelectSlice(chartData[index]?.key)}
          >
            {chartData.map((entry) => (
              <Cell
                key={entry.key}
                fill={colors[entry.key]}
                stroke={activeSlice === entry.key ? 'var(--text)' : 'transparent'}
                strokeWidth={activeSlice === entry.key ? 2 : 0}
                opacity={activeSlice && activeSlice !== entry.key ? 0.45 : 1}
                style={{ cursor: 'pointer' }}
              />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function TagCoverageChart({ tagCoverage, tagMissingCounts, loading, activeTag, onSelectTag }) {
  const data = useMemo(() => (
    Object.entries(tagCoverage || {}).map(([tag, pct]) => ({
      tag,
      coverage: pct,
      missing: tagMissingCounts?.[tag] ?? 0,
    }))
  ), [tagCoverage, tagMissingCounts]);

  if (loading) return <Skeleton className="h-56 rounded-xl" />;
  if (!data.length) return null;

  return (
    <div className="waste-chart-card">
      <h3 className="waste-chart-card__title">Required tag coverage</h3>
      <p className="waste-chart-card__sub">Click a bar to filter resources missing that tag</p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 12, bottom: 0, left: 4 }}
          onClick={(state) => {
            const tag = state?.activePayload?.[0]?.payload?.tag;
            if (tag) onSelectTag(tag);
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(156,163,175,0.2)" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="tag" width={96} tick={{ fontSize: 10 }} />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload;
              return (
                <div className="waste-chart-tooltip">
                  <p className="waste-chart-tooltip__title">{row.tag}</p>
                  <p className="waste-chart-tooltip__row">Coverage: <strong>{row.coverage}%</strong></p>
                  <p className="waste-chart-tooltip__row">Missing on: <strong>{row.missing}</strong></p>
                </div>
              );
            }}
          />
          <Bar dataKey="coverage" name="Coverage" radius={[0, 4, 4, 0]} cursor="pointer">
            {data.map((entry) => (
              <Cell
                key={entry.tag}
                fill={activeTag === entry.tag ? '#0f766e' : scoreColour(entry.coverage).fill}
                opacity={activeTag && activeTag !== entry.tag ? 0.45 : 0.92}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ResourceTypeChart({ rows, loading, activeType, onSelectType }) {
  const data = useMemo(() => (rows ?? []).slice(0, 8), [rows]);

  if (loading) return <Skeleton className="h-56 rounded-xl" />;
  if (!data.length) return null;

  return (
    <div className="waste-chart-card">
      <h3 className="waste-chart-card__title">Lowest compliance by resource type</h3>
      <p className="waste-chart-card__sub">Click a bar to filter</p>
      <ResponsiveContainer width="100%" height={Math.max(220, data.length * 28)}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 12, bottom: 0, left: 4 }}
          onClick={(state) => {
            const type = state?.activePayload?.[0]?.payload?.resource_type;
            if (type) onSelectType(type);
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(156,163,175,0.2)" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10 }} />
          <YAxis
            type="category"
            dataKey="resource_type"
            width={110}
            tick={{ fontSize: 10 }}
            tickFormatter={(v) => (v.length > 18 ? `${v.slice(0, 16)}…` : v)}
          />
          <Tooltip />
          <Bar dataKey="score_pct" name="Compliance" radius={[0, 4, 4, 0]} cursor="pointer">
            {data.map((entry, index) => (
              <Cell
                key={entry.resource_type}
                fill={activeType === entry.resource_type ? '#0f766e' : CHART_COLORS[index % CHART_COLORS.length]}
                opacity={activeType && activeType !== entry.resource_type ? 0.45 : 0.92}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function scoreMeterClass(pct) {
  if (pct == null) return 'tag-score-meter__value';
  if (pct >= 90) return 'tag-score-meter__value tag-score-meter__value--good';
  if (pct >= 70) return 'tag-score-meter__value tag-score-meter__value--warn';
  return 'tag-score-meter__value tag-score-meter__value--bad';
}

function ScoreMeter({ pct, compact = false }) {
  const colours = scoreColour(pct);
  return (
    <div className={`tag-score-meter${compact ? ' tag-score-meter--compact' : ''}`}>
      <div className="tag-score-meter__track">
        <div
          className="tag-score-meter__fill"
          style={{ width: `${pct ?? 0}%`, background: colours.fill }}
        />
      </div>
      <span className={scoreMeterClass(pct)}>{pct ?? 0}%</span>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="tag-rg-explorer__skeleton" aria-hidden>
      <div className="tag-rg-explorer__skeleton-line" />
      <div className="tag-rg-explorer__skeleton-line" />
      <div className="tag-rg-explorer__skeleton-line" />
      <div className="tag-rg-explorer__skeleton-line" style={{ width: '72%' }} />
    </div>
  );
}

function RgGroupList({ groups, loading, activeGroup, onSelectGroup }) {
  if (loading) return <TableSkeleton />;
  if (!groups?.length) {
    return <div className="tag-rg-explorer__empty">No resource groups in this subscription.</div>;
  }

  return (
    <div className="tag-rg-explorer__scroll">
      <table className="tag-rg-table">
        <thead>
          <tr>
            {['Resource group', 'Total', 'Score'].map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => {
            const isActive = activeGroup === group.resource_group;
            return (
              <tr
                key={group.resource_group}
                className={`tag-rg-table__row${isActive ? ' tag-rg-table__row--active' : ''}`}
                onClick={() => onSelectGroup(group.resource_group)}
                tabIndex={0}
                role="button"
                aria-selected={isActive}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectGroup(group.resource_group);
                  }
                }}
              >
                <td className="tag-rg-table__group-name" title={group.resource_group}>
                  {group.resource_group}
                </td>
                <td className="tag-rg-table__count">
                  <span>{group.compliant}</span>/{group.total}
                </td>
                <td>
                  <ScoreMeter pct={group.score_pct} compact />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const NC_COLS = [
  { key: 'resource_name', label: 'Resource' },
  { key: 'resource_type', label: 'Type' },
  { key: 'resource_group', label: 'Resource group' },
  { key: 'compliance_pct', label: 'Tag coverage' },
  { key: 'missing_tags', label: 'Missing tags' },
];

function ResourceListTable({ items, loading, onSelectRow, hideResourceGroup = false, emptyMessage = 'No resources match your filters.' }) {
  const [sortKey, setSortKey] = useState('compliance_pct');
  const [sortDir, setSortDir] = useState('asc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const cols = useMemo(
    () => (hideResourceGroup ? NC_COLS.filter((c) => c.key !== 'resource_group') : NC_COLS),
    [hideResourceGroup],
  );

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

  useEffect(() => setPage(1), [items, sortKey, sortDir, pageSize]);

  function toggleSort(key) {
    if (key === sortKey) setSortDir((dir) => (dir === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('asc'); }
    setPage(1);
  }

  if (loading) return <TableSkeleton />;

  if (!sorted.length) {
    return <div className="tag-rg-explorer__empty">{emptyMessage}</div>;
  }

  return (
    <>
      <div className="tag-rg-explorer__scroll">
        <table className="tag-rg-table">
          <thead>
            <tr>
              {cols.map((col) => (
                <th
                  key={col.key}
                  className={`tag-rg-table__th--sortable${sortKey === col.key ? ' tag-rg-table__th--active' : ''}`}
                  onClick={() => toggleSort(col.key)}
                >
                  <span className="tag-rg-table__sort">
                    {col.label}
                    {sortKey === col.key && (sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageItems.map((row) => (
              <tr
                key={row.resource_id}
                className="tag-rg-table__row"
                onClick={() => onSelectRow(row)}
                tabIndex={0}
                role="button"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectRow(row);
                  }
                }}
              >
                <td className="tag-rg-table__name" title={row.resource_name}>
                  {row.resource_name || '—'}
                </td>
                <td className="tag-rg-table__mono" title={row.resource_type}>
                  {row.resource_type}
                </td>
                {!hideResourceGroup && (
                  <td className="tag-rg-table__mono" title={row.resource_group}>
                    {row.resource_group}
                  </td>
                )}
                <td>
                  <ScoreMeter pct={row.compliance_pct} />
                </td>
                <td>
                  <div className="flex flex-wrap gap-1">
                    {(row.missing_tags || []).map((tag) => (
                      <span key={tag} className="tag-cell tag-cell--missing">{tag}</span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <PaginationControls
        page={page}
        pageSize={pageSize}
        total={sorted.length}
        onPageChange={setPage}
        onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
      />
    </>
  );
}

function RgExplorer({
  groups,
  items,
  allCount,
  loading,
  activeGroup,
  onSelectGroup,
  onSelectRow,
}) {
  const activeGroupMeta = useMemo(
    () => (groups ?? []).find((g) => g.resource_group === activeGroup),
    [groups, activeGroup],
  );

  const groupItems = useMemo(() => {
    if (!activeGroup) return items;
    return items.filter(
      (row) => (row.resource_group || '').toLowerCase() === activeGroup.toLowerCase(),
    );
  }, [items, activeGroup]);

  return (
    <div className="tag-rg-explorer mb-5">
      <div className="tag-rg-explorer__header">
        <div>
          <h3 className="tag-rg-explorer__title">Resource groups and compliance</h3>
          <p className="tag-rg-explorer__sub">
            Select a resource group to review its non-compliant resources alongside the list.
          </p>
        </div>
        {activeGroup && (
          <button
            type="button"
            className="chip active"
            onClick={() => onSelectGroup('')}
          >
            Clear selection
            <X size={12} aria-hidden />
          </button>
        )}
      </div>

      <div className="tag-rg-explorer__grid">
        <div className="tag-rg-explorer__pane tag-rg-explorer__pane--groups">
          <div className="tag-rg-explorer__pane-head">
            <p className="tag-rg-explorer__pane-title">Resource groups</p>
            <p className="tag-rg-explorer__pane-meta">
              {(groups ?? []).length.toLocaleString()} groups · worst compliance first
            </p>
          </div>
          <RgGroupList
            groups={groups}
            loading={loading}
            activeGroup={activeGroup}
            onSelectGroup={onSelectGroup}
          />
        </div>

        <div className="tag-rg-explorer__pane tag-rg-explorer__pane--resources">
          <div className="tag-rg-explorer__pane-head">
            <p className="tag-rg-explorer__pane-title">
              {activeGroup ? 'Resources in group' : 'Non-compliant resources'}
            </p>
            <p className="tag-rg-explorer__pane-meta">
              {activeGroup ? (
                <>
                  <code className="tag-rg-explorer__mono">{activeGroup}</code>
                  {activeGroupMeta ? (
                    <> · {activeGroupMeta.compliant}/{activeGroupMeta.total} compliant ({activeGroupMeta.score_pct}%)</>
                  ) : null}
                  {' · '}{groupItems.length.toLocaleString()} showing
                </>
              ) : (
                <>
                  {groupItems.length.toLocaleString()} showing
                  {allCount !== groupItems.length ? ` of ${allCount.toLocaleString()}` : ''}
                  {' · '}Select a group on the left to focus
                </>
              )}
            </p>
          </div>
          {activeGroup ? (
            <ResourceListTable
              items={groupItems}
              loading={loading}
              onSelectRow={onSelectRow}
              hideResourceGroup
              emptyMessage="No non-compliant resources in this group match your filters."
            />
          ) : (
            <div className="tag-rg-explorer__empty">
              <span className="tag-rg-explorer__empty-icon" aria-hidden>→</span>
              <strong>Select a resource group</strong>
              <span>Resources for that group will appear here without leaving this view.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ActiveFilterChips({ filters, onClearMissingTag, onClearGroup, onClearType, onClearSlice }) {
  const chips = [];
  if (filters.missingTag) chips.push({ key: 'tag', label: `Missing ${filters.missingTag}`, onClear: onClearMissingTag });
  if (filters.resourceGroup) chips.push({ key: 'rg', label: filters.resourceGroup, onClear: onClearGroup });
  if (filters.resourceType) chips.push({ key: 'type', label: filters.resourceType, onClear: onClearType });
  if (filters.complianceSlice === 'compliant') chips.push({ key: 'slice', label: 'Fully compliant resources', onClear: onClearSlice });
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

export default function TagCompliancePage() {
  const { subscription, subscriptionLabel } = useAdvancedSubscription();
  const [requiredTags, setRequiredTags] = useState(DEFAULT_TAGS);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS, complianceSlice: '' });
  const [selectedResource, setSelectedResource] = useState(null);

  const load = useCallback(async () => {
    if (!subscription?.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchComplianceScore(subscription, { required_tags: requiredTags });
      setData(result);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [subscription, requiredTags]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    setFilters({ ...EMPTY_FILTERS, complianceSlice: '' });
    setSelectedResource(null);
  }, [subscription]);

  const allNonCompliant = data?.non_compliant_resources ?? [];
  const filteredItems = useMemo(() => {
    let rows = applyTagFilters(allNonCompliant, filters);
    if (filters.complianceSlice === 'compliant') rows = [];
    return rows;
  }, [allNonCompliant, filters]);

  const hasFilters = !!(
    filters.search.trim()
    || filters.resourceGroup
    || filters.resourceType
    || filters.missingTag
    || filters.complianceSlice
  );

  const groupOptions = useMemo(() => (
    [...new Set((data?.groups ?? []).map((g) => g.resource_group))].map((g) => ({ value: g, label: g }))
  ), [data?.groups]);

  const typeOptions = useMemo(() => (
    [...new Set((data?.by_resource_type ?? []).map((t) => t.resource_type))].map((t) => ({ value: t, label: t }))
  ), [data?.by_resource_type]);

  return (
    <AdvancedToolLayout
      title="Tag compliance"
      subtitle="Measure tagging coverage across active inventory resources — spot gaps and focus remediation."
      iconKey="tagCompliance"
      iconRoute="/tag-compliance"
      accent="tags"
      hasHeroBand
      metaItems={[
        data?.total_resources != null && `${data.total_resources.toLocaleString()} resources`,
        data?.overall_score != null && `Score: ${Math.round(data.overall_score)}%`,
        requiredTags.length && `Required tags: ${requiredTags.join(', ')}`,
      ].filter(Boolean)}
      onRefresh={load}
      loading={loading}
      error={error}
      errorTitle="Could not load tag compliance"
    >
      <TagComplianceHero
        subscriptionLabel={subscriptionLabel}
        data={data}
        loading={loading}
        requiredTags={requiredTags}
        onRequiredTagsChange={setRequiredTags}
        activeMissingTag={filters.missingTag}
        onMissingTagClick={(tag) => {
          setFilters((f) => ({ ...f, missingTag: f.missingTag === tag ? '' : tag, complianceSlice: '' }));
        }}
      />

      <TagComplianceDataNote data={data} />

      <FilterBar
        className="waste-filter-bar"
        search={{
          value: filters.search,
          onChange: (search) => setFilters((f) => ({ ...f, search })),
          placeholder: 'Search resources, groups, or types…',
        }}
        selects={[
          {
            id: 'rg',
            label: 'Resource group',
            value: filters.resourceGroup,
            onChange: (resourceGroup) => setFilters((f) => ({ ...f, resourceGroup })),
            options: [{ value: '', label: 'All resource groups' }, ...groupOptions],
          },
          {
            id: 'type',
            label: 'Resource type',
            value: filters.resourceType,
            onChange: (resourceType) => setFilters((f) => ({ ...f, resourceType })),
            options: [{ value: '', label: 'All resource types' }, ...typeOptions],
          },
        ]}
        onClear={hasFilters ? () => setFilters({ ...EMPTY_FILTERS, complianceSlice: '' }) : undefined}
        resultCount={{
          shown: filteredItems.length,
          total: data?.non_compliant_count ?? 0,
          label: 'non-compliant resources',
        }}
      />

      <ActiveFilterChips
        filters={filters}
        onClearMissingTag={() => setFilters((f) => ({ ...f, missingTag: '' }))}
        onClearGroup={() => setFilters((f) => ({ ...f, resourceGroup: '' }))}
        onClearType={() => setFilters((f) => ({ ...f, resourceType: '' }))}
        onClearSlice={() => setFilters((f) => ({ ...f, complianceSlice: '' }))}
      />

      <div className="waste-charts-grid mb-5">
        <ComplianceDonut
          data={data}
          loading={loading}
          activeSlice={filters.complianceSlice}
          onSelectSlice={(slice) => {
            setFilters((f) => ({
              ...f,
              complianceSlice: f.complianceSlice === slice ? '' : slice,
            }));
          }}
        />
        <TagCoverageChart
          tagCoverage={data?.tag_coverage_pct}
          tagMissingCounts={data?.tag_missing_counts}
          loading={loading}
          activeTag={filters.missingTag}
          onSelectTag={(tag) => {
            setFilters((f) => ({ ...f, missingTag: f.missingTag === tag ? '' : tag, complianceSlice: '' }));
          }}
        />
      </div>

      <div className="mb-5">
        <ResourceTypeChart
          rows={data?.by_resource_type}
          loading={loading}
          activeType={filters.resourceType}
          onSelectType={(resourceType) => {
            setFilters((f) => ({ ...f, resourceType: f.resourceType === resourceType ? '' : resourceType }));
          }}
        />
      </div>

      <RgExplorer
        groups={data?.groups}
        items={filteredItems}
        allCount={data?.non_compliant_count ?? 0}
        loading={loading}
        activeGroup={filters.resourceGroup}
        onSelectGroup={(resourceGroup) => {
          setFilters((f) => ({
            ...f,
            resourceGroup: f.resourceGroup === resourceGroup ? '' : resourceGroup,
          }));
        }}
        onSelectRow={(row) => setSelectedResource({
          id: row.resource_id,
          resource_id: row.resource_id,
          name: row.resource_name,
          resource_name: row.resource_name,
          type: row.resource_type,
          resource_type: row.resource_type,
          resource_group: row.resource_group,
        })}
      />

      <ResourceInsightDrawer
        resource={selectedResource}
        findings={[]}
        onClose={() => setSelectedResource(null)}
        title="Resource"
        iconKey="tagCompliance"
        indexReady
      />
    </AdvancedToolLayout>
  );
}

export { applyTagFilters, scoreColour };
