import React, { useContext, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AppCtx } from '../../../App';
import {
  fetchFindings, updateFindingStatus,
} from '../../../api/azure';
import { getErrorMessage } from '../../../api/errors';
import {
  SeverityBadge, CategoryBadge, StatusBadge,
} from '../../FindingBadges';
import {
  LoadingState, EmptyState, QueryErrorState,
} from '../../QueryStates';
import { formatCurrency } from '../../../utils/format';
import { sumUnifiedSavingsForFindings } from '../../../utils/unifiedSavings';
import { toDisplayText } from '../../../utils/formatDisplay';
import FindingEvidence from '../../FindingEvidence';
import FindingResourceLinks from '../../FindingResourceLinks';
import AssetIcon from '../../AssetIcon';
import { iconFromResourceId, iconForCategory } from '../../../config/assetIcons';
import { FINDINGS_INDEX_LIMIT } from '../../../hooks/useFindingsIndex';
import WizCommandBar from '../WizCommandBar';
import WizResourceNameLink from '../WizResourceNameLink';
import WhatIfScenarioPanel from '../WhatIfScenarioPanel';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

function IssueDetail({ finding, currency, onStatus, pending }) {
  if (!finding) {
    return (
      <aside className="wiz-detail wiz-split__detail">
        <div className="wiz-empty">
          <strong>Select an issue</strong>
          Review rule details, evidence, savings impact, and what-if scenarios.
        </div>
      </aside>
    );
  }

  const whatIf = finding.evidence?.what_if || null;
  const resourceName = finding.resource_name || (finding.resource_id || '').split('/').pop();

  return (
    <aside className="wiz-detail wiz-split__detail wiz-detail--elevated">
      <header className="wiz-detail__head">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', flexWrap: 'wrap' }}>
          <SeverityBadge severity={finding.severity} />
          <CategoryBadge category={finding.category} />
        </div>
        <h2 style={{ marginTop: '0.5rem' }}>{finding.rule_name}</h2>
        <p style={{ margin: '0.5rem 0 0', color: 'var(--text2)', fontSize: '0.85rem' }}>
          {toDisplayText(finding.description)}
        </p>
      </header>
      <div className="wiz-detail__body">
        <div className="wiz-detail__meta-grid">
          <div className="wiz-meta-item">
            <label>Resource</label>
            <span>{resourceName}</span>
          </div>
          <div className="wiz-meta-item">
            <label>Est. savings/mo</label>
            <span className="wiz-savings-cell wiz-savings-cell--positive">
              {finding.estimated_savings_usd > 0
                ? formatCurrency(finding.estimated_savings_usd, { currency, decimals: 0 })
                : '—'}
            </span>
          </div>
          <div className="wiz-meta-item">
            <label>Status</label>
            <span><StatusBadge status={finding.status} /></span>
          </div>
          <div className="wiz-meta-item">
            <label>Confidence</label>
            <span>{finding.confidence_score ? `${finding.confidence_score}%` : '—'}</span>
          </div>
          <div className="wiz-meta-item">
            <label>Priority</label>
            <span>{finding.action_priority || '—'}</span>
          </div>
        </div>

        <WhatIfScenarioPanel
          scenario={whatIf}
          currency={currency}
          monthlyCost={finding.estimated_monthly_cost || finding.evidence?.monthly_cost || 0}
          finding={finding}
        />

        <FindingResourceLinks finding={finding} />
        <FindingEvidence finding={finding} />

        <div className="wiz-detail__actions">
          {finding.resource_id && (
            <Link
              to={`/action-centre?resource=${encodeURIComponent(finding.resource_id)}&inspect=1&section=advanced-analysis`}
              className="btn btn-secondary btn-sm"
            >
              Open in action centre
            </Link>
          )}
          {finding.status === 'open' && (
            <>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={pending}
                onClick={() => onStatus(finding.id, 'acknowledged')}
              >
                Acknowledge
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={pending}
                onClick={() => onStatus(finding.id, 'ignored')}
              >
                Ignore
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={pending}
                onClick={() => onStatus(finding.id, 'resolved')}
              >
                Resolve
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}

export default function WizIssuesPanel() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const qc = useQueryClient();
  const [sevFilter, setSevFilter] = useState('');
  const [statusFilter, setStatus] = useState('open');
  const [catFilter, setCatFilter] = useState('');
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState(null);
  const [actionError, setActionError] = useState('');
  const [filterCritical, setFilterCritical] = useState(false);
  const [filterHighSavings, setFilterHighSavings] = useState(false);
  const [sortBy, setSortBy] = useState('severity');

  const {
    data: findings = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['wiz-findings', subscription, sevFilter, catFilter, statusFilter],
    queryFn: () => fetchFindings({
      subscription_id: subscription,
      severity: sevFilter || undefined,
      category: catFilter || undefined,
      status: statusFilter || undefined,
      limit: FINDINGS_INDEX_LIMIT,
    }),
    enabled: !!subscription,
  });

  const categories = useMemo(
    () => [...new Set(findings.map((f) => f.category).filter(Boolean))],
    [findings],
  );

  const chipCounts = useMemo(() => {
    let critical = 0;
    let highSav = 0;
    for (const f of findings) {
      if (['CRITICAL', 'HIGH'].includes(f.severity)) critical += 1;
      if ((f.estimated_savings_usd || 0) >= 100) highSav += 1;
    }
    return { critical, highSav };
  }, [findings]);

  const filtered = useMemo(() => {
    let list = findings;
    if (filterCritical) {
      list = list.filter((f) => ['CRITICAL', 'HIGH'].includes(f.severity));
    }
    if (filterHighSavings) {
      list = list.filter((f) => (f.estimated_savings_usd || 0) >= 100);
    }
    if (q.trim()) {
      const hay = q.trim().toLowerCase();
      list = list.filter((f) => {
        const text = `${f.rule_name} ${f.resource_name} ${f.resource_id} ${f.category}`.toLowerCase();
        return text.includes(hay);
      });
    }
    const sorted = [...list];
    const sevRank = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 };
    sorted.sort((a, b) => {
      if (sortBy === 'savings') {
        return (b.estimated_savings_usd || 0) - (a.estimated_savings_usd || 0);
      }
      if (sortBy === 'name') {
        return (a.rule_name || '').localeCompare(b.rule_name || '');
      }
      const sd = (sevRank[a.severity] ?? 9) - (sevRank[b.severity] ?? 9);
      if (sd !== 0) return sd;
      return (b.estimated_savings_usd || 0) - (a.estimated_savings_usd || 0);
    });
    return sorted;
  }, [findings, q, filterCritical, filterHighSavings, sortBy]);

  const filteredSavings = useMemo(
    () => sumUnifiedSavingsForFindings(filtered),
    [filtered],
  );

  const hasActiveFilters = Boolean(
    q.trim()
    || filterCritical
    || filterHighSavings
    || sevFilter
    || catFilter
    || (statusFilter && statusFilter !== 'open'),
  );

  const mut = useMutation({
    mutationFn: ({ id, status }) => updateFindingStatus(id, status, subscription),
    onMutate: () => setActionError(''),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wiz-findings'] });
      qc.invalidateQueries({ queryKey: ['findings'] });
      qc.invalidateQueries({ queryKey: ['findings-index'] });
      qc.invalidateQueries({ queryKey: ['findings-summary'] });
    },
    onError: (err) => setActionError(getErrorMessage(err, 'Could not update finding status.')),
  });

  const onStatus = (id, status) => {
    mut.mutate({ id, status }, {
      onSuccess: () => {
        if (selected?.id === id) {
          setSelected((prev) => (prev ? { ...prev, status } : prev));
        }
      },
    });
  };

  if (!subscription) {
    return (
      <div className="wiz-empty">
        <strong>Select a subscription</strong>
        Choose a subscription to review optimization issues.
      </div>
    );
  }

  return (
    <div className="wiz-panel" id="wiz-panel-issues" role="tabpanel" aria-labelledby="wiz-tab-issues">
      {actionError && (
        <div className="alert alert--danger" role="alert">{actionError}</div>
      )}

      {hasActiveFilters && filtered.length > 0 && (
        <div className="wiz-filter-summary" role="status" style={{ marginBottom: '0.75rem' }}>
          <span className="wiz-pill wiz-pill--ok">
            Filtered:
            {' '}
            {formatCurrency(filteredSavings, { currency, decimals: 0 })}
            /mo ·
            {' '}
            {filtered.length.toLocaleString()}
            {' '}
            issues
          </span>
        </div>
      )}

      <div className="wiz-split wiz-split--immersive">
        <section className="wiz-card">
          <header className="wiz-card__head">
            <h3>Issues</h3>
            <span className="wiz-pill">{filtered.length.toLocaleString()} shown</span>
          </header>

          <WizCommandBar
            search={q}
            onSearchChange={setQ}
            searchPlaceholder="Search issues, resources, categories…"
            sort={sortBy}
            onSortChange={setSortBy}
            sortOptions={[
              { value: 'severity', label: 'Sort: severity' },
              { value: 'savings', label: 'Sort: savings' },
              { value: 'name', label: 'Sort: name' },
            ]}
            chips={[
              {
                id: 'critical',
                label: 'Critical / high',
                count: chipCounts.critical,
                active: filterCritical,
                onClick: () => setFilterCritical((v) => !v),
              },
              {
                id: 'savings',
                label: 'Savings $100+',
                count: chipCounts.highSav,
                active: filterHighSavings,
                onClick: () => setFilterHighSavings((v) => !v),
              },
            ]}
          >
            <select
              className="wiz-command-select"
              value={sevFilter}
              onChange={(e) => setSevFilter(e.target.value)}
              aria-label="Severity"
            >
              <option value="">All severities</option>
              {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select
              className="wiz-command-select"
              value={catFilter}
              onChange={(e) => setCatFilter(e.target.value)}
              aria-label="Category"
            >
              <option value="">All categories</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select
              className="wiz-command-select"
              value={statusFilter}
              onChange={(e) => setStatus(e.target.value)}
              aria-label="Status"
            >
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
              <option value="ignored">Ignored</option>
              <option value="">All</option>
            </select>
          </WizCommandBar>

          <div className="wiz-results-summary">
            <span>
              Showing <strong>{filtered.length.toLocaleString()}</strong> issues
            </span>
            <span className="wiz-results-summary__savings">
              {formatCurrency(filteredSavings, { currency, decimals: 0 })} recoverable/mo in view
            </span>
          </div>

          {isLoading && <LoadingState message="Loading issues…" />}
          {isError && <QueryErrorState error={error} onRetry={refetch} />}
          {!isLoading && !isError && filtered.length === 0 && (
            <EmptyState message="No issues match your filters." />
          )}

          {!isLoading && !isError && filtered.length > 0 && (
            <div className="wiz-table-wrap wiz-table-wrap--immersive">
              <table className="wiz-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Issue</th>
                    <th>Resource</th>
                    <th>Category</th>
                    <th>Savings</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((f) => {
                    const priorityClass = f.severity === 'CRITICAL'
                      ? 'wiz-row--priority-critical'
                      : f.severity === 'HIGH'
                        ? 'wiz-row--priority-high'
                        : '';
                    return (
                      <tr
                        key={f.id}
                        className={`${selected?.id === f.id ? 'wiz-row--selected' : ''} ${priorityClass}`.trim()}
                        onClick={() => setSelected(f)}
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setSelected(f);
                          }
                        }}
                      >
                        <td><SeverityBadge severity={f.severity} /></td>
                        <td style={{ fontWeight: 500, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {f.rule_name}
                        </td>
                        <td>
                          <div className="wiz-resource-cell">
                            <AssetIcon
                              iconKey={iconFromResourceId(f.resource_id) || iconForCategory(f.category)}
                              size={18}
                            />
                            <div style={{ minWidth: 0 }}>
                              <div className="wiz-resource-cell__name">
                                <WizResourceNameLink
                                  resourceId={f.resource_id}
                                  name={f.resource_name || (f.resource_id || '').split('/').pop()}
                                />
                              </div>
                              {f.resource_group && (
                                <div className="wiz-resource-cell__meta">{f.resource_group}</div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td><CategoryBadge category={f.category} /></td>
                        <td className={`wiz-savings-cell${f.estimated_savings_usd > 0 ? ' wiz-savings-cell--positive' : ''}`}>
                          {f.estimated_savings_usd > 0
                            ? formatCurrency(f.estimated_savings_usd, { currency, decimals: 0 })
                            : '—'}
                        </td>
                        <td><StatusBadge status={f.status} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <IssueDetail
          finding={selected}
          currency={currency}
          onStatus={onStatus}
          pending={mut.isPending}
        />
      </div>
    </div>
  );
}
