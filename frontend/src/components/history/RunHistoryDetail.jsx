import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ChevronLeft, ChevronRight, X, ArrowRight, ExternalLink,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { fetchRun } from '../../api/azure';
import FilterBar from '../FilterBar';
import RecommendationDetailCard from '../RecommendationDetailCard';
import RunHistoryJobStatus from './RunHistoryJobStatus';
import { SeverityBadge } from '../FindingBadges';
import {
  LoadingState, QueryErrorState, EmptyState,
} from '../QueryStates';
import { PAGE_ICONS } from '../../config/assetIcons';
import { resolveResourceAppHref } from '../../utils/armResourceLinks';
import { formatCurrency, formatDateTime } from '../../utils/format';
import { matchFinding } from '../../utils/filterUtils';
import { sumUnifiedSavingsForFindings } from '../../utils/unifiedSavings';
import { jobStatusLabel, jobStatusTone } from '../../utils/runHistoryUtils';
import { useAuth } from '../../context/AuthContext';
import { genericLoadingMessage } from '../../utils/viewerUi';

const SEV_OPTIONS = ['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

export default function RunHistoryDetail({
  item,
  items,
  currency = 'CAD',
  subscriptionId,
  onClose,
  onSelectItem,
}) {
  const { isAdmin } = useAuth();
  const [search, setSearch] = useState('');
  const [sevFilter, setSevFilter] = useState('');
  const [catFilter, setCatFilter] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [viewMode, setViewMode] = useState('table');

  const run = item?.run || null;
  const job = item?.job || null;
  const runId = item?.runId;
  const hasRun = !!runId;

  const { data: detail, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['run-detail', runId, subscriptionId],
    queryFn: () => fetchRun(runId, subscriptionId),
    enabled: !!runId && !!subscriptionId,
  });

  const detailJob = detail?.job || job;

  const itemIndex = items.findIndex((entry) => entry.key === item?.key);
  const prevItem = itemIndex > 0 ? items[itemIndex - 1] : null;
  const nextItem = itemIndex >= 0 && itemIndex < items.length - 1 ? items[itemIndex + 1] : null;

  const findings = useMemo(() => detail?.findings || [], [detail?.findings]);

  const categories = useMemo(
    () => [...new Set(findings.map((f) => f.category).filter(Boolean))].sort(),
    [findings],
  );

  const filtered = useMemo(() => findings.filter((f) => {
    if (sevFilter && f.severity !== sevFilter) return false;
    if (catFilter && f.category !== catFilter) return false;
    return matchFinding(f, search);
  }), [findings, sevFilter, catFilter, search]);

  const totalSavings = useMemo(
    () => sumUnifiedSavingsForFindings(filtered),
    [filtered],
  );
  const hasFilters = !!(search || sevFilter || catFilter);

  const clearFilters = () => {
    setSearch('');
    setSevFilter('');
    setCatFilter('');
  };

  const critical = item?.critical ?? 0;
  const high = item?.high ?? 0;
  const headerDate = item?.analyzedAt ? formatDateTime(item.analyzedAt) : 'Job details';

  return (
    <section className="run-history-detail" aria-label="Run details">
      <header className="run-history-detail__header">
        <nav className="run-history-detail__breadcrumb" aria-label="Breadcrumb">
          <button type="button" className="run-history-detail__back" onClick={onClose}>
            Run history
          </button>
          <span aria-hidden>/</span>
          <span>{headerDate}</span>
        </nav>

        <div className="run-history-detail__actions">
          <div className="run-history-detail__nav">
            <button
              type="button"
              className="btn btn-ghost btn-icon-only"
              disabled={!prevItem}
              onClick={() => prevItem && onSelectItem(prevItem)}
              aria-label="Previous job"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-icon-only"
              disabled={!nextItem}
              onClick={() => nextItem && onSelectItem(nextItem)}
              aria-label="Next job"
            >
              <ChevronRight size={16} />
            </button>
          </div>
          <button type="button" className="btn btn-ghost btn-icon-only" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
      </header>

      <div className="run-history-detail__summary">
        <div className="run-history-detail__kpis">
          <div>
            <span className="run-history-detail__kpi-label">Status</span>
            <strong>
              <span className={`badge badge-${jobStatusTone(item.status)}`}>
                {jobStatusLabel(item.status, item.statusLabel)}
              </span>
            </strong>
          </div>
          {hasRun && (
            <div>
              <span className="run-history-detail__kpi-label">Findings</span>
              <strong>{item.total_findings ?? 0}</strong>
            </div>
          )}
          {hasRun && (
            <div>
              <span className="run-history-detail__kpi-label">Critical / high</span>
              <strong>{critical} / {high}</strong>
            </div>
          )}
          {hasRun && (
            <div>
              <span className="run-history-detail__kpi-label">Est. savings</span>
              <strong className="run-history-detail__savings">
                {formatCurrency(item.total_savings_usd || 0, { currency, decimals: 0 })}
              </strong>
            </div>
          )}
          <div>
            <span className="run-history-detail__kpi-label">Engine</span>
            <strong>{item.engine_version || 'standard'}</strong>
          </div>
          <div>
            <span className="run-history-detail__kpi-label">Profile</span>
            <strong>{item.profile || 'default'}</strong>
          </div>
        </div>
        {hasRun && (
          <Link to="/action-centre" className="btn btn-ghost btn-sm">
            Compare with current recommendations
            <ArrowRight size={14} />
          </Link>
        )}
      </div>

      {isAdmin && <RunHistoryJobStatus job={detailJob} currency={currency} />}

      {!hasRun && (
        <EmptyState
          iconKey={PAGE_ICONS.history}
          message={item.status === 'failed'
            ? 'This job did not complete successfully, so no run findings were saved.'
            : 'This job has not produced a saved run yet.'}
        />
      )}

      {hasRun && isLoading && <LoadingState message={genericLoadingMessage(isAdmin, 'Loading run findings…')} />}
      {hasRun && isError && <QueryErrorState error={error} onRetry={refetch} title="Failed to load run" />}

      {hasRun && !isLoading && !isError && (
        <>
          <FilterBar
            search={{
              value: search,
              onChange: setSearch,
              placeholder: 'Search rule, resource, or detail…',
            }}
            selects={[
              {
                id: 'severity',
                label: 'Severity',
                value: sevFilter,
                onChange: setSevFilter,
                options: [
                  { value: '', label: 'All severities' },
                  ...SEV_OPTIONS.filter(Boolean).map((s) => ({ value: s, label: s })),
                ],
              },
              {
                id: 'category',
                label: 'Category',
                value: catFilter,
                onChange: setCatFilter,
                options: [
                  { value: '', label: 'All categories' },
                  ...categories.map((c) => ({ value: c, label: c })),
                ],
              },
            ]}
            onClear={hasFilters ? clearFilters : undefined}
            resultCount={{
              shown: filtered.length,
              total: findings.length,
              label: 'findings',
            }}
          />

          <div className="run-history-detail__toolbar">
            <span className="run-history-detail__filtered-savings">
              Filtered savings: {formatCurrency(totalSavings, { currency, decimals: 0 })}/mo
            </span>
            <div className="rec-view-toggle">
              <button
                type="button"
                className={`btn btn-ghost btn-sm${viewMode === 'table' ? ' active' : ''}`}
                onClick={() => setViewMode('table')}
              >
                Table
              </button>
              <button
                type="button"
                className={`btn btn-ghost btn-sm${viewMode === 'cards' ? ' active' : ''}`}
                onClick={() => setViewMode('cards')}
              >
                Details
              </button>
            </div>
          </div>

          {filtered.length === 0 && (
            <EmptyState
              iconKey={PAGE_ICONS.history}
              message="No findings match your filters for this run."
            />
          )}

          {filtered.length > 0 && viewMode === 'table' && (
            <div className="table-wrap run-history-detail__table">
              <table>
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Rule</th>
                    <th>Resource</th>
                    <th>Savings</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((f) => {
                    const fid = f.id || `${f.rule_id}-${f.resource_id}`;
                    const isOpen = expandedId === fid;
                    return (
                      <React.Fragment key={fid}>
                        <tr
                          className={`run-history-detail__row${isOpen ? ' run-history-detail__row--open' : ''}`}
                          onClick={() => setExpandedId(isOpen ? null : fid)}
                        >
                          <td><SeverityBadge severity={f.severity} size={11} /></td>
                          <td className="run-history-detail__rule">{f.rule_name}</td>
                          <td className="run-history-detail__resource" title={f.resource_id}>
                            {f.resource_name || f.resource_id?.split('/').pop()}
                          </td>
                          <td className="run-history-detail__savings-cell">
                            {f.estimated_savings_usd > 0
                              ? formatCurrency(f.estimated_savings_usd, { currency, decimals: 0 })
                              : '—'}
                          </td>
                          <td className="run-history-detail__links" onClick={(e) => e.stopPropagation()}>
                            {resolveResourceAppHref(f) && (
                              <Link
                                to={resolveResourceAppHref(f)}
                                className="btn btn-ghost btn-sm"
                                title="Open in action centre"
                              >
                                <ArrowRight size={12} />
                              </Link>
                            )}
                            {f.azure_portal_url && (
                              <a
                                href={f.azure_portal_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn btn-ghost btn-sm"
                                title="Open in Azure"
                              >
                                <ExternalLink size={12} />
                              </a>
                            )}
                          </td>
                        </tr>
                        {isOpen && (
                          <tr className="run-history-detail__expand">
                            <td colSpan={5}>
                              <RecommendationDetailCard
                                finding={f}
                                currency={currency}
                                defaultExpanded
                              />
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {filtered.length > 0 && viewMode === 'cards' && (
            <div className="run-history-detail__cards">
              {filtered.map((f) => (
                <RecommendationDetailCard
                  key={f.id || `${f.rule_id}-${f.resource_id}`}
                  finding={f}
                  currency={currency}
                  defaultExpanded={filtered.length <= 3}
                />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
