import React, { useContext, useMemo, useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { AppCtx } from '../App';
import { useAuth } from '../context/AuthContext';
import { useOperationProgress } from '../context/OperationProgressContext';
import { fetchRuns, fetchAnalysisJobs } from '../api/azure';
import useJobProgressSSE from '../hooks/useJobProgressSSE';
import PageHeader from '../components/PageHeader';
import PageHero from '../components/layout/PageHero';
import AssetIcon from '../components/AssetIcon';
import FilterBar from '../components/FilterBar';
import RunHistoryDetail from '../components/history/RunHistoryDetail';
import AnalysisJobProgress from '../components/optimization/AnalysisJobProgress';
import { QueryErrorState, SubscriptionRequired, LoadingState, EmptyState } from '../components/QueryStates';
import { genericLoadingMessage } from '../utils/viewerUi';
import { PAGE_ICONS } from '../config/assetIcons';
import { formatCurrency, formatDateTime } from '../utils/format';
import { textIncludes, uniqueSorted } from '../utils/filterUtils';
import { buildRunHistoryItems, jobStatusLabel, jobStatusTone } from '../utils/runHistoryUtils';

export default function RunHistory() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const { syncing, syncLabel, job: trackedJob } = useOperationProgress();
  const currency = billingCurrency || 'CAD';
  const [searchParams, setSearchParams] = useSearchParams();

  const [search, setSearch] = useState(() => searchParams.get('q') || '');
  const [engineFilter, setEngineFilter] = useState(() => searchParams.get('engine') || '');
  const [profileFilter, setProfileFilter] = useState(() => searchParams.get('profile') || '');

  const selectedRunId = searchParams.get('run');

  const { data: runs = [], isLoading, isError, error, refetch } = useQuery({
    queryKey: ['runs', subscription],
    queryFn: () => fetchRuns({ subscription_id: subscription, limit: 100 }),
    enabled: !!subscription,
  });

  const handleJobEvent = React.useCallback((evt) => {
    if (!evt?.job) return;
    queryClient.setQueryData(['analysis-jobs-active', subscription], (prev = []) => {
      const rows = Array.isArray(prev) ? [...prev] : [];
      const idx = rows.findIndex((j) => j.id === evt.job.id);
      if (idx >= 0) rows[idx] = evt.job;
      else rows.unshift(evt.job);
      return rows;
    });
    queryClient.invalidateQueries({ queryKey: ['analysis-jobs', subscription] });
    if (evt.job.status === 'completed' || evt.job.status === 'failed') {
      refetch();
    }
  }, [queryClient, subscription, refetch]);

  const { connected: sseConnected } = useJobProgressSSE(subscription, {
    enabled: !!subscription,
    onEvent: handleJobEvent,
  });

  const { data: jobs = [], refetch: refetchJobs } = useQuery({
    queryKey: ['analysis-jobs', subscription],
    queryFn: () => fetchAnalysisJobs({ subscription_id: subscription, limit: 100 }),
    enabled: !!subscription,
    refetchInterval: (q) => {
      const rows = q.state.data || [];
      const hasActive = rows.some((j) => j.is_active || j.status === 'queued' || j.status === 'running');
      if (sseConnected && hasActive) return 15000;
      return hasActive || syncing ? 2000 : 30000;
    },
  });

  const {
    data: activeJobs = [],
    refetch: refetchActiveJobs,
  } = useQuery({
    queryKey: ['analysis-jobs-active', subscription],
    queryFn: () => fetchAnalysisJobs({ subscription_id: subscription, active_only: true, limit: 5 }),
    enabled: !!subscription,
    refetchInterval: (q) => {
      const rows = q.state.data || [];
      if (sseConnected && rows.length > 0) return 15000;
      return rows.length > 0 || syncing ? 2000 : 15000;
    },
  });

  const activeJob = useMemo(() => {
    if (trackedJob?.is_active || trackedJob?.status === 'queued' || trackedJob?.status === 'running') {
      return trackedJob;
    }
    return activeJobs[0] || null;
  }, [trackedJob, activeJobs]);

  useEffect(() => {
    if (activeJob?.status === 'completed' || activeJob?.status === 'failed') {
      refetch();
      refetchJobs();
      queryClient.invalidateQueries({ queryKey: ['analysis-jobs-active', subscription] });
    }
  }, [activeJob?.status, activeJob?.run_id, refetch, refetchJobs, queryClient, subscription]);

  const historyItems = useMemo(
    () => buildRunHistoryItems(runs, jobs),
    [runs, jobs],
  );

  const engines = useMemo(
    () => uniqueSorted(historyItems.map((r) => r.engine_version || 'standard')),
    [historyItems],
  );
  const profiles = useMemo(
    () => uniqueSorted(historyItems.map((r) => r.profile || 'default')),
    [historyItems],
  );

  const filteredItems = useMemo(() => historyItems.filter((item) => {
    if (engineFilter && (item.engine_version || 'standard') !== engineFilter) return false;
    if (profileFilter && (item.profile || 'default') !== profileFilter) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      textIncludes(item.key, q)
      || textIncludes(item.runId, q)
      || textIncludes(item.jobId, q)
      || textIncludes(item.engine_version, q)
      || textIncludes(item.profile, q)
      || textIncludes(item.statusLabel, q)
      || textIncludes(item.scopeLabel, q)
      || textIncludes(formatDateTime(item.analyzedAt), q)
    );
  }), [historyItems, engineFilter, profileFilter, search]);

  const selectedItem = useMemo(
    () => historyItems.find((item) => item.key === selectedRunId) || null,
    [historyItems, selectedRunId],
  );

  const hasFilters = !!(search || engineFilter || profileFilter);

  const writeParams = ({
    runId = selectedRunId,
    q = search,
    engine = engineFilter,
    profile = profileFilter,
  } = {}) => {
    const params = new URLSearchParams();
    if (runId) params.set('run', runId);
    if (q) params.set('q', q);
    if (engine) params.set('engine', engine);
    if (profile) params.set('profile', profile);
    setSearchParams(params, { replace: true });
  };

  const openRun = (item) => {
    writeParams({ runId: item.key });
  };
  const closeRun = () => {
    writeParams({ runId: null });
  };

  const clearFilters = () => {
    setSearch('');
    setEngineFilter('');
    setProfileFilter('');
    writeParams({ q: '', engine: '', profile: '' });
  };

  const onSearchChange = (v) => {
    setSearch(v);
    writeParams({ q: v });
  };

  const onEngineChange = (v) => {
    setEngineFilter(v);
    writeParams({ engine: v });
  };

  const onProfileChange = (v) => {
    setProfileFilter(v);
    writeParams({ profile: v });
  };

  const critCount = (item) => item.critical ?? 0;
  const highCount = (item) => item.high ?? 0;

  const totalSavings = useMemo(
    () => historyItems.reduce((sum, item) => sum + (item.total_savings_usd || 0), 0),
    [historyItems],
  );

  const latestCompleted = historyItems.find((item) => item.status === 'completed' && item.runId);

  return (
    <div className="page-shell run-history-page">
      <PageHeader
        title="Run history"
        iconKey={PAGE_ICONS.history}
        pageScope="runHistory"
      />

      {subscription && (
        <PageHero
          variant="history-hero"
          eyebrow="Analysis"
          title="Past optimization runs"
          subtitle={`${historyItems.length.toLocaleString()} jobs stored · ${filteredItems.length.toLocaleString()} showing`}
          isLoading={isLoading && historyItems.length === 0}
          metrics={[
            { label: 'Total jobs', value: historyItems.length.toLocaleString(), tone: 'default' },
            {
              label: 'Latest findings',
              value: latestCompleted?.total_findings?.toLocaleString() ?? '—',
              tone: 'default',
            },
            {
              label: 'Latest savings',
              value: latestCompleted
                ? formatCurrency(latestCompleted.total_savings_usd || 0, { currency, decimals: 0 })
                : '—',
              tone: 'success',
            },
            {
              label: 'Total savings tracked',
              value: formatCurrency(totalSavings, { currency, decimals: 0 }),
              tone: 'success',
            },
          ]}
          actions={[
            { id: 'recs', label: 'Action centre', href: '/action-centre' },
          ]}
        />
      )}

      {!subscription && <SubscriptionRequired />}

      {subscription && (
        <>
          <FilterBar
            search={{
              value: search,
              onChange: onSearchChange,
              placeholder: 'Search by date, engine, or profile…',
            }}
            selects={[
              {
                id: 'engine',
                label: 'Engine',
                value: engineFilter,
                onChange: onEngineChange,
                options: [
                  { value: '', label: 'All engines' },
                  ...engines.map((e) => ({ value: e, label: e })),
                ],
              },
              {
                id: 'profile',
                label: 'Profile',
                value: profileFilter,
                onChange: onProfileChange,
                options: [
                  { value: '', label: 'All profiles' },
                  ...profiles.map((p) => ({ value: p, label: p })),
                ],
              },
            ]}
            onClear={hasFilters ? clearFilters : undefined}
            resultCount={{
              shown: filteredItems.length,
              total: historyItems.length,
              label: 'jobs',
            }}
          />

          {isAdmin && (syncing || activeJob) && (
            <div className="run-history-active">
              {syncing && !activeJob && (
                <section className="run-history-sync-banner card" aria-live="polite" aria-busy="true">
                  <RefreshCw size={16} className="spin" aria-hidden />
                  <div>
                    <strong>Sync in progress</strong>
                    <p>{syncLabel || 'Syncing from Azure…'}</p>
                  </div>
                </section>
              )}
              {activeJob && (
                <AnalysisJobProgress
                  job={activeJob}
                  onRefresh={() => {
                    refetchActiveJobs();
                    refetchJobs();
                    if (trackedJob?.id) {
                      queryClient.invalidateQueries({ queryKey: ['analysis-job', trackedJob.id] });
                    }
                  }}
                  currency={currency}
                  variant="history"
                  onOpenRun={(runId) => writeParams({ runId })}
                />
              )}
            </div>
          )}

          <div className={`run-history-layout${selectedItem ? ' run-history-layout--detail' : ''}`}>
            <div className="run-history-list card">
              {isLoading && <LoadingState message={genericLoadingMessage(isAdmin, 'Loading run history…')} />}
              {isError && <QueryErrorState error={error} onRetry={refetch} />}
              {!isLoading && !isError && filteredItems.length === 0 && (
                <EmptyState
                  iconKey={PAGE_ICONS.history}
                  message={hasFilters
                    ? 'No jobs match your filters.'
                    : (isAdmin
                      ? 'No jobs yet. Sync and analyze from Sync center.'
                      : 'No analysis jobs yet.')}
                />
              )}

              {!isLoading && !isError && filteredItems.length > 0 && (
                <div className="table-wrap">
                  <table className="run-history-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Status</th>
                        <th>Engine</th>
                        <th>Profile</th>
                        <th>Scope</th>
                        <th>Findings</th>
                        <th>Savings</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredItems.map((item) => (
                        <tr
                          key={item.key}
                          className={`run-history-table__row${selectedRunId === item.key ? ' run-history-table__row--active' : ''}`}
                          onClick={() => openRun(item)}
                        >
                          <td className="run-history-table__date">
                            <AssetIcon iconKey={PAGE_ICONS.history} size={14} alt="" />
                            {item.analyzedAt ? formatDateTime(item.analyzedAt) : '—'}
                          </td>
                          <td>
                            <span className={`badge badge-${jobStatusTone(item.status)}`}>
                              {jobStatusLabel(item.status, item.statusLabel)}
                            </span>
                          </td>
                          <td><span className="badge badge-medium">{item.engine_version || 'standard'}</span></td>
                          <td><span className="badge badge-info">{item.profile || 'default'}</span></td>
                          <td className="run-history-table__scope">{item.scopeLabel || '—'}</td>
                          <td>
                            {item.runId ? (
                              <>
                                <span className="run-history-table__findings">{item.total_findings ?? 0}</span>
                                {(critCount(item) > 0 || highCount(item) > 0) && (
                                  <span className="run-history-table__sev">
                                    {critCount(item) > 0 && <span className="run-history-table__crit">{critCount(item)} crit</span>}
                                    {highCount(item) > 0 && <span>{highCount(item)} high</span>}
                                  </span>
                                )}
                              </>
                            ) : (
                              <span className="run-history-table__muted">—</span>
                            )}
                          </td>
                          <td className="run-history-table__savings">
                            {item.runId
                              ? formatCurrency(item.total_savings_usd || 0, { currency, decimals: 0 })
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {selectedItem && (
              <div className="run-history-detail-panel card">
                <RunHistoryDetail
                  item={selectedItem}
                  items={filteredItems}
                  currency={currency}
                  subscriptionId={subscription}
                  onClose={closeRun}
                  onSelectItem={openRun}
                />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
