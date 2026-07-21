import React, { useCallback, useContext, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { syncResources } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { isSyncAcceptResponse } from '../utils/asyncAcceptUtils';
import { useOperationProgress } from '../context/OperationProgressContext';
import { useToast } from '../context/ToastContext';

/**
 * Trigger Azure → DB unified sync pipeline and invalidate related React Query caches.
 *
 * Sync POST returns immediately (202). Progress and completion are handled by
 * OperationProgressContext via /sync/pipeline polling.
 */
export default function useResourceSync({
  subscription,
  invalidateKeys = [],
  onAnalysisComplete,
  syncTypes = null,
  analyzeComponents = null,
  includeCosts = true,
  progressLabel = null,
}) {
  const queryClient = useQueryClient();
  const { reloadSubscriptions } = useContext(AppCtx);
  const { beginSync, endSync, startPipelineSync } = useOperationProgress();
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
    setMessage('Starting sync…');
    setError(false);
    try {
      const params = { subscription_id: subscription };
      if (syncTypes?.length) {
        params.types = syncTypes.join(',');
      }
      params.include_costs = includeCosts;
      if (analyzeComponents?.length) {
        params.components = analyzeComponents.join(',');
      }
      const result = await syncResources(params);

      const accepted = isSyncAcceptResponse(result, result?.httpStatus);

      if (accepted) {
        startPipelineSync(subscription, {
          label: 'Running full sync pipeline',
          initialPipeline: result.pipeline,
          invalidateKeys,
          onComplete: onAnalysisComplete,
          runAdvisor: !syncTypes?.length,
          reloadSubscriptions,
        });
        setMessage('Sync running in the background…');
        setSyncing(false);
        const toastMsg = result?.recovered
          ? 'Sync started. The server was slow to respond — track progress in the bar at the top.'
          : 'Sync started. Track progress in the bar at the top.';
        showToast(toastMsg, { variant: 'info' });
        return { accepted: true, async: true, pipeline: result.pipeline };
      }

      // Legacy synchronous response (wait=true)
      endSync();
      setSyncing(false);
      if (result?.analysis?.job_id) {
        showToast('Sync complete.', { variant: 'success' });
      }
      await Promise.all(
        invalidateKeys.map((key) => queryClient.invalidateQueries({ queryKey: key })),
      );
      if (reloadSubscriptions) {
        await reloadSubscriptions();
      }
      setMessage('');
      return result;
    } catch (err) {
      const msg = getErrorMessage(err, 'Sync failed. Please try again.');
      showToast(msg, { variant: 'error' });
      setMessage('');
      setError(true);
      endSync();
      setSyncing(false);
      throw err;
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
    startPipelineSync,
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
