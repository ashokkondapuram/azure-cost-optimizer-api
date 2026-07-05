import { useState, useCallback, useContext } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { syncResources, syncAzureAdvisorRecommendations } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { toDisplayText } from '../utils/formatDisplay';
import { useOperationProgress } from '../context/OperationProgressContext';
import { useToast } from '../context/ToastContext';

/**
 * Trigger Azure → DB sync and invalidate related React Query caches.
 *
 * @param {object} options
 * @param {string} options.subscription - Azure subscription ID
 * @param {string[][]} [options.invalidateKeys] - queryKey prefixes to invalidate on success
 * @param {function} [options.onAnalysisComplete] - callback when analysis is queued or completes
 * @param {string[]} [options.syncTypes] - canonical types to sync (scoped); omit for full sync
 * @param {string[]} [options.analyzeComponents] - optimization components for scoped analysis
 * @param {boolean} [options.includeCosts] - sync cost export with scoped sync
 */
export default function useResourceSync({
  subscription,
  invalidateKeys = [],
  onAnalysisComplete,
  syncTypes = null,
  analyzeComponents = null,
  includeCosts = false,
  progressLabel = null,
}) {
  const queryClient = useQueryClient();
  const { reloadSubscriptions } = useContext(AppCtx);
  const { beginSync, endSync, trackJob } = useOperationProgress();
  const { showToast } = useToast();
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);

  const sync = useCallback(async () => {
    if (!subscription) return null;
    if (Array.isArray(syncTypes) && syncTypes.length === 0) {
      const msg = 'This page is not configured for scoped sync.';
      showToast(msg, { variant: 'error' });
      setError(true);
      return null;
    }
    const label = progressLabel || (syncTypes?.length ? 'Syncing resources' : 'Syncing from Azure');
    beginSync(label);
    setSyncing(true);
    setMessage('');
    setError(false);
    let advisorResult = null;
    try {
      const params = { subscription_id: subscription };
      if (syncTypes?.length) {
        params.types = syncTypes.join(',');
        params.include_costs = includeCosts;
      } else if (includeCosts) {
        params.include_costs = true;
      }
      if (analyzeComponents?.length) {
        params.components = analyzeComponents.join(',');
      }
      const result = await syncResources(params);
      let advisorResult = null;
      if (!syncTypes?.length) {
        try {
          advisorResult = await syncAzureAdvisorRecommendations({ subscription_id: subscription });
        } catch (advisorErr) {
          advisorResult = { error: getErrorMessage(advisorErr, 'Advisor sync failed') };
        }
      }
      await Promise.all(
        invalidateKeys.map((key) =>
          queryClient.invalidateQueries({ queryKey: key }),
        ),
      );
      if (!syncTypes?.length) {
        await queryClient.invalidateQueries({ queryKey: ['advisor-index', subscription] });
        await queryClient.invalidateQueries({ queryKey: ['dashboard-overview', subscription] });
      }
      if (!syncTypes?.length) {
        await queryClient.invalidateQueries({
          predicate: (q) => Array.isArray(q.queryKey)
            && typeof q.queryKey[0] === 'string'
            && q.queryKey[0].startsWith('/resources'),
        });
      }
      if (reloadSubscriptions) {
        await reloadSubscriptions();
      }
      const resourceCounts = result?.synced?.resources || {};
      const armTotal = Object.values(resourceCounts).reduce((sum, n) => sum + (n || 0), 0);
      const dbTotal = result?.synced?.db_total;
      const scopedTypes = result?.synced?.types;
      let msg = '';
      let isError = false;
      if (dbTotal === 0 || (dbTotal == null && armTotal === 0)) {
        msg = scopedTypes?.length
          ? 'Sync finished but nothing was saved for this resource type. Retry or check Azure permissions.'
          : 'Sync finished but nothing was saved to the database. Pages will load live from Azure until sync succeeds.';
        isError = true;
        setError(true);
      } else if (scopedTypes?.length) {
        msg = `Synced ${armTotal.toLocaleString()} ${scopedTypes.length === 1 ? 'resource' : 'resources'} from Azure`;
      } else {
        msg = `Synced ${(dbTotal ?? armTotal).toLocaleString()} resources to the database`;
      }
      const analysis = result?.analysis;
      if (analysis?.status === 'error') {
        msg += `. Analysis failed: ${toDisplayText(analysis.error || 'Unable to start analysis')}`;
        isError = true;
        setError(true);
      } else if (analysis?.status === 'queued' && analysis?.job_id) {
        trackJob(analysis.job_id);
        msg += '. Analysis started in the background';
        if (onAnalysisComplete) onAnalysisComplete();
      } else if (analysis?.summary) {
        const findings = analysis.summary.total_findings ?? 0;
        const savings = analysis.summary.total_estimated_monthly_savings_usd ?? 0;
        msg += `. ${findings.toLocaleString()} recommendations saved (${Math.round(savings).toLocaleString()} est. savings/mo)`;
        if (onAnalysisComplete) onAnalysisComplete();
      }
      if (advisorResult?.error) {
        msg += `. Advisor sync failed: ${toDisplayText(advisorResult.error)}`;
        isError = true;
        setError(true);
      } else if (advisorResult?.stored != null || advisorResult?.fetched != null) {
        const stored = advisorResult.stored ?? 0;
        const fetched = advisorResult.fetched ?? 0;
        if (fetched > 0) {
          msg += `. ${stored.toLocaleString()} Advisor recommendations saved`;
        } else if (!syncTypes?.length) {
          msg += '. No Azure Advisor recommendations returned';
        }
      }
      showToast(msg, { variant: isError ? 'error' : 'success' });
      setMessage('');
      return { ...result, advisor: advisorResult };
    } catch (err) {
      const msg = getErrorMessage(err, 'Sync failed. Please try again.');
      showToast(msg, { variant: 'error' });
      setMessage('');
      setError(true);
      throw err;
    } finally {
      endSync();
      setSyncing(false);
    }
  }, [
    subscription,
    invalidateKeys,
    syncTypes,
    analyzeComponents,
    includeCosts,
    progressLabel,
    beginSync,
    endSync,
    trackJob,
    queryClient,
    reloadSubscriptions,
    onAnalysisComplete,
    showToast,
  ]);

  const clearMessage = useCallback(() => {
    setMessage('');
    setError(false);
  }, []);

  return { sync, syncing, message, error, clearMessage };
}
