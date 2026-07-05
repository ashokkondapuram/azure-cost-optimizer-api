import React, { useContext, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { fetchFindings, updateFindingStatus } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import PageHeader from '../components/PageHeader';
import {
  SeverityBadge, CategoryBadge, StatusBadge,
} from '../components/FindingBadges';
import {
  LoadingState, SubscriptionRequired, EmptyState, QueryErrorState,
} from '../components/QueryStates';
import {
  Filter, FolderOpen, DollarSign, Target, BarChart3,
  Lightbulb, MapPin, FileJson, Eye, CheckCircle2, XCircle, X,
  AzureResourceIcon,
} from '../components/FinOpsIcons';
import { PAGE_ICONS, iconForCategory, iconFromResourceId } from '../config/assetIcons';
import { formatCurrency } from '../utils/format';
import { toDisplayText } from '../utils/formatDisplay';
import FindingEvidence from '../components/FindingEvidence';
import FindingResourceLinks from '../components/FindingResourceLinks';

export default function Findings() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const qc = useQueryClient();
  const [sevFilter, setSevFilter] = useState('');
  const [catFilter, setCatFilter] = useState('');
  const [statusFilter, setStatus] = useState('open');
  const [selected, setSelected] = useState(null);
  const [actionError, setActionError] = useState('');

  const {
    data: findings = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['findings', subscription, sevFilter, catFilter, statusFilter],
    queryFn: () => fetchFindings({
      subscription_id: subscription,
      severity: sevFilter || undefined,
      category: catFilter || undefined,
      status: statusFilter || undefined,
      limit: 500,
    }),
    enabled: !!subscription,
  });

  const mut = useMutation({
    mutationFn: ({ id, status }) => updateFindingStatus(id, status),
    onMutate: () => setActionError(''),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['findings'] });
      qc.invalidateQueries({ queryKey: ['findings-summary'] });
    },
    onError: (err) => setActionError(getErrorMessage(err, 'Could not update finding status.')),
  });

  const categories = [...new Set(findings.map((f) => f.category))];

  return (
    <div>
      <PageHeader
        title="Findings"
        iconKey={PAGE_ICONS.findings}
        subtitle={
          subscription
            ? `${findings.length} findings in the selected subscription`
            : 'Select a subscription to review findings'
        }
      />

      {actionError && (
        <div className="alert alert--danger" role="alert" style={{ marginBottom: '1rem' }}>
          {actionError}
        </div>
      )}

      {!subscription && <SubscriptionRequired />}

      {subscription && (
        <>
          <div className="toolbar" style={{ marginBottom: '1rem' }}>
            <span className="toolbar-icon-label"><Filter size={13} /> Severity</span>
            <select value={sevFilter} onChange={(e) => setSevFilter(e.target.value)} aria-label="Severity filter">
              <option value="">All severities</option>
              {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <span className="toolbar-icon-label"><FolderOpen size={13} /> Category</span>
            <select value={catFilter} onChange={(e) => setCatFilter(e.target.value)} aria-label="Category filter">
              <option value="">All categories</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <span className="toolbar-icon-label"><Target size={13} /> Status</span>
            <select value={statusFilter} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
              <option value="ignored">Ignored</option>
              <option value="">All</option>
            </select>
          </div>

          {isLoading && <LoadingState message="Loading findings…" />}
          {isError && <QueryErrorState error={error} onRetry={refetch} />}
          {!isLoading && !isError && findings.length === 0 && (
            <EmptyState
              iconKey={PAGE_ICONS.findings}
              message="No findings. Sync and analyze from Optimization center or adjust filters."
            />
          )}

          {!isLoading && !isError && findings.length > 0 && (
            <div className="card">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Severity</th>
                      <th>Rule</th>
                      <th>Resource</th>
                      <th>Category</th>
                      <th>Est. savings/mo</th>
                      <th>Priority</th>
                      <th>Confidence</th>
                      <th>Score</th>
                      <th>Status</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {findings.map((f) => (
                      <tr key={f.id} className="finding-row" onClick={() => setSelected(f)}>
                        <td><SeverityBadge severity={f.severity} /></td>
                        <td style={{ color: 'var(--text)', fontWeight: 500, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {f.rule_name}
                        </td>
                        <td style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <span className="icon-inline" title={f.resource_id}>
                            <AzureResourceIcon
                              type={null}
                              src={iconFromResourceId(f.resource_id) || iconForCategory(f.category)}
                              size={18}
                            />
                            <span>{f.resource_name || (f.resource_id || '').split('/').pop()}</span>
                          </span>
                          {f.resource_group && (
                            <div className="icon-inline" style={{ fontSize: '0.72rem', color: 'var(--text3)', marginTop: 2 }}>
                              <FolderOpen size={11} />
                              {f.resource_group}
                            </div>
                          )}
                        </td>
                        <td><CategoryBadge category={f.category} /></td>
                        <td style={{ color: f.estimated_savings_usd > 0 ? 'var(--success)' : 'var(--text3)', fontWeight: 600 }}>
                          <span className="icon-inline">
                            {f.estimated_savings_usd > 0 && <DollarSign size={13} />}
                            {f.estimated_savings_usd > 0
                              ? formatCurrency(f.estimated_savings_usd, { currency, decimals: 0 })
                              : '\u2014'}
                          </span>
                        </td>
                        <td>
                          {f.action_priority
                            ? <span className="badge badge-info badge--with-icon"><Target size={11} />{f.action_priority}</span>
                            : <span style={{ color: 'var(--text3)' }}>{'\u2014'}</span>}
                        </td>
                        <td style={{ fontSize: '0.78rem', color: 'var(--text2)' }}>
                          {f.confidence_score ? (
                            <span className="icon-inline">
                              <BarChart3 size={12} style={{ opacity: 0.7 }} />
                              {f.confidence_score}%
                            </span>
                          ) : '\u2014'}
                        </td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <div className="progress-bar-bg" style={{ width: 60 }}>
                              <div
                                className="progress-bar-fill"
                                style={{
                                  width: `${f.waste_score || 0}%`,
                                  background: f.waste_score > 75
                                    ? 'var(--danger)'
                                    : f.waste_score > 50
                                      ? 'var(--warning)'
                                      : 'var(--success)',
                                }}
                              />
                            </div>
                            <span style={{ fontSize: '0.78rem' }}>{f.waste_score}</span>
                          </div>
                        </td>
                        <td><StatusBadge status={f.status} /></td>
                        <td>
                          <div style={{ display: 'flex', gap: 6 }} onClick={(e) => e.stopPropagation()}>
                            {f.status === 'open' && (
                              <>
                                <button
                                  type="button"
                                  className="btn btn-ghost btn-icon-only"
                                  title="Acknowledge"
                                  aria-label="Acknowledge finding"
                                  disabled={mut.isPending}
                                  onClick={() => mut.mutate({ id: f.id, status: 'acknowledged' })}
                                >
                                  <Eye size={14} />
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-ghost btn-icon-only"
                                  title="Resolve"
                                  aria-label="Resolve finding"
                                  disabled={mut.isPending}
                                  onClick={() => mut.mutate({ id: f.id, status: 'resolved' })}
                                >
                                  <CheckCircle2 size={14} />
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)} role="presentation">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="finding-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem' }}>
              <div>
                <div id="finding-modal-title" className="modal-title" style={{ marginBottom: 6 }}>{selected.rule_name}</div>
                <SeverityBadge severity={selected.severity} />
                {' '}
                <CategoryBadge category={selected.category} />
              </div>
              <button type="button" className="btn btn-ghost btn-icon-only" onClick={() => setSelected(null)} aria-label="Close">
                <X size={16} />
              </button>
            </div>

            <div style={{ display: 'grid', gap: '0.75rem', fontSize: '0.86rem' }}>
              <div>
                <strong className="icon-inline">
                  <AzureResourceIcon
                    type={null}
                    src={iconFromResourceId(selected.resource_id) || iconForCategory(selected.category)}
                    size={16}
                  />
                  Resource
                </strong>
                <br />
                <span style={{ color: 'var(--text2)', wordBreak: 'break-all' }}>{selected.resource_id}</span>
              </div>

              <div>
                <strong className="icon-inline"><FileJson size={14} /> Detail</strong>
                <br />
                <span style={{ color: 'var(--text2)' }}>{toDisplayText(selected.detail)}</span>
              </div>

              <div style={{ background: 'rgba(37,99,235,0.08)', border: '1px solid rgba(37,99,235,0.2)', borderRadius: 8, padding: '0.75rem' }}>
                <strong className="icon-inline" style={{ color: 'var(--primary)' }}>
                  <Lightbulb size={14} /> Recommendation
                </strong>
                <br />
                <span style={{ color: 'var(--text2)' }}>{toDisplayText(selected.recommendation)}</span>
              </div>

              <FindingResourceLinks finding={selected} />

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem' }}>
                <div style={{ background: 'var(--bg3)', borderRadius: 8, padding: '0.6rem 0.75rem' }}>
                  <div className="icon-inline" style={{ fontSize: '0.7rem', color: 'var(--text3)', marginBottom: 2 }}>
                    <DollarSign size={12} /> Est. monthly savings
                  </div>
                  <div style={{ fontWeight: 700, color: selected.estimated_savings_usd > 0 ? 'var(--success)' : 'var(--text3)' }}>
                    {selected.estimated_savings_usd > 0
                      ? formatCurrency(selected.estimated_savings_usd, { currency })
                      : 'N/A'}
                  </div>
                </div>
                <div style={{ background: 'var(--bg3)', borderRadius: 8, padding: '0.6rem 0.75rem' }}>
                  <div className="icon-inline" style={{ fontSize: '0.7rem', color: 'var(--text3)', marginBottom: 2 }}>
                    <BarChart3 size={12} /> Waste score
                  </div>
                  <div style={{ fontWeight: 700, color: selected.waste_score > 75 ? 'var(--danger)' : selected.waste_score > 50 ? 'var(--warning)' : 'var(--success)' }}>
                    {selected.waste_score} / 100
                  </div>
                </div>
                <div style={{ background: 'var(--bg3)', borderRadius: 8, padding: '0.6rem 0.75rem' }}>
                  <div className="icon-inline" style={{ fontSize: '0.7rem', color: 'var(--text3)', marginBottom: 2 }}>
                    Status
                  </div>
                  <div style={{ fontWeight: 700 }}><StatusBadge status={selected.status} /></div>
                </div>
              </div>

              {selected.resource_group && (
                <div>
                  <strong className="icon-inline"><FolderOpen size={14} /> Resource group</strong>
                  <br />
                  <span style={{ color: 'var(--text2)' }}>{selected.resource_group}</span>
                </div>
              )}

              {selected.location && (
                <div>
                  <strong className="icon-inline"><MapPin size={14} /> Location</strong>
                  <br />
                  <span style={{ color: 'var(--text2)' }}>{selected.location}</span>
                </div>
              )}

              {selected.annualized_savings_usd > 0 && (
                <div style={{ background: 'rgba(34,197,94,0.07)', border: '1px solid rgba(34,197,94,0.18)', borderRadius: 8, padding: '0.75rem' }}>
                  <strong className="icon-inline" style={{ color: 'var(--success)' }}>
                    <DollarSign size={14} /> Annualized savings
                  </strong>
                  <br />
                  <span style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--success)' }}>
                    {formatCurrency(selected.annualized_savings_usd, { currency, decimals: 0 })} / year
                  </span>
                </div>
              )}

              {selected.confidence_score != null && (
                <div>
                  <strong className="icon-inline"><BarChart3 size={14} /> Confidence</strong>
                  <br />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                    <div className="progress-bar-bg" style={{ width: 120 }}>
                      <div className="progress-bar-fill" style={{ width: `${selected.confidence_score}%`, background: 'var(--primary)' }} />
                    </div>
                    <span style={{ fontSize: '0.82rem' }}>{selected.confidence_score}%</span>
                  </div>
                </div>
              )}

              {selected.action_priority && (
                <div>
                  <strong className="icon-inline"><Target size={14} /> Action priority</strong>
                  {' '}
                  <span className="badge badge-medium">{selected.action_priority}</span>
                </div>
              )}

              {selected.impact && (
                <div>
                  <strong className="icon-inline"><Lightbulb size={14} /> Impact</strong>
                  <br />
                  <span style={{ color: 'var(--text2)' }}>{toDisplayText(selected.impact)}</span>
                </div>
              )}

              {selected.evidence && Object.keys(selected.evidence).length > 0 && (
                <div>
                  <strong>How we determined this</strong>
                  <FindingEvidence
                    evidence={selected.evidence}
                    context={{ resourceId: selected.resource_id || '' }}
                  />
                </div>
              )}

              <div style={{ display: 'flex', gap: 8, marginTop: '0.5rem', flexWrap: 'wrap' }}>
                {selected.status === 'open' && (
                  <>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={mut.isPending}
                      onClick={() => { mut.mutate({ id: selected.id, status: 'acknowledged' }); setSelected(null); }}
                    >
                      <Eye size={14} /> Acknowledge
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={mut.isPending}
                      onClick={() => { mut.mutate({ id: selected.id, status: 'resolved' }); setSelected(null); }}
                    >
                      <CheckCircle2 size={14} /> Mark resolved
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger"
                      disabled={mut.isPending}
                      onClick={() => { mut.mutate({ id: selected.id, status: 'ignored' }); setSelected(null); }}
                    >
                      <XCircle size={14} /> Ignore
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
