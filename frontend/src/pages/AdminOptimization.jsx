import React, { useContext, useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Play, RefreshCw, ChevronRight,
  Layers, Settings2, Loader2, Lightbulb,
} from 'lucide-react';
import { AppCtx } from '../App';
import {
  fetchOptimizationOverview,
  startBatchAnalysis,
  cancelAnalysisJob,
  syncAzureAdvisorRecommendations,
} from '../api/azure';
import PageHeader from '../components/PageHeader';
import PageHero from '../components/layout/PageHero';
import OptimizationHubLinks from '../components/navigation/OptimizationHubLinks';
import AnalysisJobProgress from '../components/optimization/AnalysisJobProgress';
import AssetIcon from '../components/AssetIcon';
import { iconForComponent } from '../config/assetIcons';
import { formatCurrency, formatDateTime } from '../utils/format';
import { getErrorMessage } from '../api/errors';
import useResourceSync from '../hooks/useResourceSync';
import { useOperationProgress } from '../context/OperationProgressContext';
import { useToast } from '../context/ToastContext';
import { engineRulesUrl } from '../utils/engineRoutes';
import {
  OPTIMIZATION_SCOPE_GROUPS,
  getOptimizationSyncScope,
  isScopedOptimization,
  optimizationScopesByKind,
} from '../utils/optimizationSyncScope';

const SEV_COLORS = {
  CRITICAL: '#dc2626',
  HIGH: '#f97316',
  MEDIUM: '#f59e0b',
  LOW: '#22c55e',
  INFO: '#6366f1',
};

function ComponentCard({ row, billingCurrency }) {
  const idlePct = row.resource_count
    ? Math.round((row.idle_or_unused_count / row.resource_count) * 100)
    : 0;
  const rulesUrl = engineRulesUrl(row.component);

  return (
    <div className="opt-component-card card">
      <div className="opt-component-card__head">
        <AssetIcon iconKey={iconForComponent(row.component)} size={22} />
        <div>
          <h3>
            <Link to={rulesUrl} className="link-subtle">{row.component}</Link>
          </h3>
          <p>{row.resource_count} resources · {row.enabled_rules}/{row.total_rules} rules on</p>
        </div>
        {row.open_findings > 0 && (
          <span className="badge badge--warning">{row.open_findings} open</span>
        )}
      </div>

      <div className="opt-component-card__stats">
        <div>
          <span className="label">Open findings</span>
          <strong>{row.open_findings}</strong>
        </div>
        <div>
          <span className="label">Waste signals</span>
          <strong className={row.idle_or_unused_count > 0 ? 'text-warning' : ''}>
            {row.idle_or_unused_count}
            {row.resource_count > 0 && <small> ({idlePct}%)</small>}
          </strong>
        </div>
        <div>
          <span className="label">Potential savings</span>
          <strong className="text-success">
            {formatCurrency(row.estimated_savings_usd, { currency: billingCurrency })}
          </strong>
        </div>
      </div>

      {row.top_findings?.length > 0 && (
        <ul className="opt-component-card__findings">
          {row.top_findings.map((f, i) => (
            <li key={`${f.rule_id}-${i}`}>
              <span
                className="sev-dot"
                style={{ background: SEV_COLORS[f.severity] || '#94a3b8' }}
                title={f.severity}
              />
              <span className="finding-text">{f.resource_name}: {f.rule_name}</span>
              <span className="finding-savings">
                {formatCurrency(f.estimated_savings_usd, { currency: billingCurrency })}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="opt-component-card__footer">
        <Link to={rulesUrl} className="link-subtle">
          <Settings2 size={13} /> Configure rules
        </Link>
        <span className="text-muted" style={{ fontSize: '0.8rem' }}>
          {row.analyzed_resource_count} analyzed
        </span>
      </div>
    </div>
  );
}

export default function AdminOptimization() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState('default');
  const [engineVersion, setEngineVersion] = useState('extended');
  const [syncScope, setSyncScope] = useState('all');
  const [running, setRunning] = useState(false);
  const [advisorSyncing, setAdvisorSyncing] = useState(false);
  const { trackJob, job: activeJob, activeJobId, clearJob } = useOperationProgress();
  const { showToast } = useToast();

  const refreshJob = useCallback(() => {
    if (activeJobId) {
      queryClient.invalidateQueries({ queryKey: ['analysis-job', activeJobId] });
    }
  }, [activeJobId, queryClient]);

  const invalidateAll = useCallback(() => {
    if (!subscription) return;
    queryClient.invalidateQueries({ queryKey: ['opt-overview', subscription] });
    queryClient.invalidateQueries({ queryKey: ['findings-summary', subscription] });
    queryClient.invalidateQueries({ queryKey: ['findings', subscription] });
    queryClient.invalidateQueries({ queryKey: ['findings-index', subscription] });
    queryClient.invalidateQueries({ queryKey: ['advisor-index', subscription] });
    queryClient.invalidateQueries({ queryKey: ['dashboard-overview', subscription] });
    queryClient.invalidateQueries({ queryKey: ['runs', subscription] });
    queryClient.invalidateQueries({ queryKey: ['resource-counts', subscription] });
    queryClient.invalidateQueries({
      predicate: (q) => Array.isArray(q.queryKey)
        && typeof q.queryKey[0] === 'string'
        && q.queryKey[0].startsWith('/resources'),
    });
  }, [queryClient, subscription]);

  const cancelJob = useCallback(async () => {
    if (!activeJobId || !subscription) return;
    try {
      await cancelAnalysisJob(activeJobId, subscription);
      refreshJob();
      clearJob();
      showToast('Analysis cancelled.', { variant: 'info' });
      invalidateAll();
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not cancel analysis.'), { variant: 'error' });
    }
  }, [activeJobId, subscription, refreshJob, clearJob, showToast, invalidateAll]);

  const scopeConfig = getOptimizationSyncScope(syncScope);
  const scoped = isScopedOptimization(syncScope);

  const { sync, syncing } = useResourceSync({
    subscription,
    syncTypes: scopeConfig.syncTypes,
    analyzeComponents: scopeConfig.components?.length ? scopeConfig.components : null,
    progressLabel: scoped ? `Syncing ${scopeConfig.label}` : 'Syncing from Azure',
    invalidateKeys: [['opt-overview', subscription], ['resource-counts', subscription], ['advisor-index', subscription], ['dashboard-overview', subscription]],
    onAnalysisComplete: invalidateAll,
  });

  const handleSync = async () => {
    try {
      const result = await sync();
      if (result?.analysis?.job_id) {
        trackJob(result.analysis.job_id);
        showToast('Sync complete — analysis running.', { variant: 'info' });
      }
    } catch {
      /* hook shows toast */
    }
  };

  const handleAdvisorSync = async () => {
    if (!subscription) return;
    setAdvisorSyncing(true);
    try {
      const result = await syncAzureAdvisorRecommendations({ subscription_id: subscription });
      invalidateAll();
      const stored = result?.stored ?? 0;
      const fetched = result?.fetched ?? 0;
      showToast(
        fetched > 0
          ? `Synced ${stored.toLocaleString()} Azure Advisor recommendations.`
          : 'Azure Advisor returned no active recommendations.',
        { variant: 'success' },
      );
    } catch (err) {
      showToast(getErrorMessage(err, 'Advisor sync failed.'), { variant: 'error' });
    } finally {
      setAdvisorSyncing(false);
    }
  };

  const { data: overview, isLoading, isError, error } = useQuery({
    queryKey: ['opt-overview', subscription, profile],
    queryFn: () => fetchOptimizationOverview({ subscription_id: subscription, profile }),
    enabled: !!subscription,
    refetchInterval: activeJobId ? 3000 : false,
  });

  useEffect(() => {
    if (activeJob?.status === 'completed') {
      invalidateAll();
    }
  }, [activeJob?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const runBatch = async () => {
    if (!subscription) return;
    setRunning(true);
    try {
      const job = await startBatchAnalysis({
        subscription_id: subscription,
        profile,
        engine_version: engineVersion,
        data_source: 'db',
        components: scopeConfig.components?.length ? scopeConfig.components : undefined,
      });
      trackJob(job.id);
      showToast(
        scoped
          ? `Batch analysis started for ${scopeConfig.label}.`
          : 'Batch analysis started — processing one component at a time.',
        { variant: 'info' },
      );
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not start batch analysis.'), { variant: 'error' });
    } finally {
      setRunning(false);
    }
  };

  const totals = overview?.totals || {};
  const components = overview?.components || [];
  const fullAnalysis = overview?.full_analysis;
  const fullAnalysisBlocked = !scoped && fullAnalysis?.enabled && fullAnalysis?.can_run === false;
  const fullAnalysisHint = fullAnalysisBlocked
    ? `Full analysis already ran${fullAnalysis?.last_run_at ? ` on ${formatDateTime(fullAnalysis.last_run_at)}` : ''}. ${
      fullAnalysis?.next_allowed_at
        ? `Next run after ${formatDateTime(fullAnalysis.next_allowed_at)}.`
        : 'Try again tomorrow.'
    } Scoped sync and analysis still work.`
    : null;

  return (
    <div className="page-shell admin-optimization-page">
      <PageHeader
        title="Optimization center"
        subtitle="Sync Azure inventory to the database, run the engine against stored resource data, and review recommendations."
        icon={<Layers size={22} />}
      />

      <PageHero
        variant="optimization-hero"
        eyebrow="Operations"
        title={subscription ? 'Sync and analyze' : 'Optimization center'}
        subtitle={
          fullAnalysisBlocked
            ? fullAnalysisHint
            : overview?.last_analyzed_at
              ? `Last analyzed ${formatDateTime(overview.last_analyzed_at)} · Full analysis limited to once every ${Math.round(fullAnalysis?.cooldown_hours || 24)} hours`
              : 'Sync inventory from Azure, then run the optimization engine against stored data.'
        }
        isLoading={subscription && isLoading && !overview}
        metrics={overview ? [
          {
            label: 'Resources',
            value: (totals.resource_count ?? 0).toLocaleString(),
            tone: 'default',
          },
          {
            label: 'Open findings',
            value: (totals.open_findings ?? 0).toLocaleString(),
            tone: (totals.open_findings ?? 0) > 0 ? 'warning' : 'default',
            href: '/recommendations',
          },
          {
            label: 'Est. savings/mo',
            value: formatCurrency(totals.estimated_savings_usd, { currency: billingCurrency, decimals: 0 }),
            tone: 'success',
            href: '/recommendations',
          },
          {
            label: 'Waste signals',
            value: (totals.idle_count ?? 0).toLocaleString(),
            tone: (totals.idle_count ?? 0) > 0 ? 'warning' : 'default',
          },
          {
            label: 'Rules enabled',
            value: `${totals.enabled_rules ?? 0}/${totals.total_rules ?? 0}`,
            tone: 'default',
            href: '/engine',
          },
        ] : []}
        actions={[
          { id: 'rules', label: 'Engine rules', href: '/engine' },
          { id: 'recs', label: 'Recommendations', href: '/recommendations' },
        ]}
      />

      <OptimizationHubLinks className="optimization-hub--page" />

      <section className="page-section card opt-actions-card">
        <div className="opt-toolbar">
        <div className="opt-toolbar__row">
          <div className="opt-toolbar__field opt-toolbar__field--grow">
            <label className="opt-toolbar__label" htmlFor="opt-sync-scope">Sync scope</label>
            <select
              id="opt-sync-scope"
              className="select-field"
              value={syncScope}
              onChange={(e) => setSyncScope(e.target.value)}
              disabled={!subscription || syncing || running || !!activeJobId}
            >
              {OPTIMIZATION_SCOPE_GROUPS.map((group) => (
                <optgroup key={group.id} label={group.label}>
                  {optimizationScopesByKind(group.id).map((scope) => (
                    <option key={scope.id} value={scope.id}>
                      {scope.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {scoped && (
              <p className="opt-toolbar__hint">
                Sync and analysis are limited to <strong>{scopeConfig.label}</strong>.
              </p>
            )}
          </div>
          <div className="opt-toolbar__field">
            <label className="opt-toolbar__label" htmlFor="opt-profile">Profile</label>
            <select
              id="opt-profile"
              className="select-field"
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
            >
              <option value="default">Default</option>
              <option value="aggressive">Aggressive</option>
              <option value="conservative">Conservative</option>
            </select>
          </div>
          <div className="opt-toolbar__field">
            <label className="opt-toolbar__label" htmlFor="opt-engine">Engine</label>
            <select
              id="opt-engine"
              className="select-field"
              value={engineVersion}
              onChange={(e) => setEngineVersion(e.target.value)}
            >
              <option value="extended">Extended</option>
              <option value="standard">Standard</option>
            </select>
          </div>
        </div>
        <div className="opt-toolbar__actions">
          <button
            type="button"
            className="btn btn--secondary"
            disabled={!subscription || advisorSyncing || syncing}
            onClick={handleAdvisorSync}
          >
            {advisorSyncing ? <Loader2 size={16} className="spin" /> : <Lightbulb size={16} />}
            Sync Advisor
          </button>
          <button
            type="button"
            className="btn btn--secondary"
            disabled={!subscription || syncing || fullAnalysisBlocked}
            title={fullAnalysisBlocked ? fullAnalysisHint : undefined}
            onClick={handleSync}
          >
            <RefreshCw size={16} className={syncing ? 'spin' : ''} />
            Sync and analyze
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={!subscription || running || !!activeJobId || fullAnalysisBlocked}
            title={fullAnalysisBlocked ? fullAnalysisHint : undefined}
            onClick={runBatch}
          >
            {running || activeJobId ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
            Re-run analysis
          </button>
          <span className="opt-toolbar__divider" aria-hidden="true" />
          <Link to="/engine" className="btn btn--ghost">
            <Settings2 size={16} /> Engine rules
          </Link>
          <Link to="/recommendations" className="btn btn--ghost">
            View recommendations <ChevronRight size={14} />
          </Link>
        </div>
        </div>
      </section>

      {(activeJobId || activeJob) && (
        <AnalysisJobProgress
          job={activeJob}
          onRefresh={refreshJob}
          onCancel={cancelJob}
          currency={billingCurrency}
        />
      )}

      {!subscription && (
        <div className="empty-state">Select a subscription to view optimization coverage.</div>
      )}

      {subscription && isLoading && <div className="loading-state">Loading optimization overview…</div>}
      {subscription && isError && (
        <div className="error-state" role="alert">{getErrorMessage(error, 'Could not load overview.')}</div>
      )}

      {subscription && overview && (
        <>
          {fullAnalysisBlocked && (
            <div className="page-callout card page-callout--info" role="status">
              <p>{fullAnalysisHint}</p>
            </div>
          )}

          {!overview.last_analyzed_at && totals.resource_count > 0 && (
            <div className="page-callout card">
              <p>
                Inventory is synced but analysis has not run yet. Use <strong>Sync from Azure</strong> or{' '}
                <strong>Re-run analysis</strong> to populate recommendations.
              </p>
            </div>
          )}

          <section className="page-section">
            <div className="section-header">
              <h2 className="section-header__title">Coverage by component</h2>
              <p className="section-header__desc">Open findings and waste signals grouped by Azure resource type.</p>
            </div>
            <div className="opt-components-grid">
            {components.map((row) => (
              <ComponentCard key={row.component} row={row} billingCurrency={billingCurrency} />
            ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
