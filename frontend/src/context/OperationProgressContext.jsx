import React, {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchAnalysisJob,
  fetchAnalysisJobs,
  fetchSyncPipelineStatus,
  syncAzureAdvisorRecommendations,
  cancelSyncPipeline,
  cancelAnalysisJob,
} from '../api/azure';
import useServerEvents from '../hooks/useServerEvents';
import { useToast } from './ToastContext';
import { useAuth } from './AuthContext';
import { getErrorMessage } from '../api/errors';
import { buildSyncPipelineToast, pipelineStageLabel } from '../utils/syncPipelineUtils';

const OperationProgressCtx = createContext(null);

function applyLatestJob(setJob, setActiveJobId, activeJobId, nextJob) {
  if (!nextJob?.id) return;
  setJob((prev) => {
    if (activeJobId && nextJob.id !== activeJobId) return prev;
    return nextJob;
  });
  if (!activeJobId && nextJob.is_active) {
    setActiveJobId(nextJob.id);
  }
}

export function OperationProgressProvider({ children, subscription, subscriptionRegistered = true }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { isAdmin } = useAuth();
  const notifiedJobRef = useRef(null);
  const notifiedPipelineRef = useRef(null);
  const activeJobIdRef = useRef(null);
  const pipelineOptionsRef = useRef(null);
  const [syncing, setSyncing] = useState(false);
  const [syncLabel, setSyncLabel] = useState('');
  const [activeJobId, setActiveJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [pipelineSubscription, setPipelineSubscription] = useState(null);
  const [pipeline, setPipeline] = useState(null);

  const pipelineActive = Boolean(
    pipelineSubscription
    && (pipeline?.pending || pipeline?.status === 'queued' || pipeline?.status === 'running'),
  );

  activeJobIdRef.current = activeJobId;

  const beginSync = useCallback((label = 'Syncing from Azure') => {
    if (!isAdmin) return;
    setSyncLabel(label);
    setSyncing(true);
  }, [isAdmin]);

  const endSync = useCallback(() => {
    if (!isAdmin) return;
    setSyncing(false);
    setSyncLabel('');
  }, [isAdmin]);

  const trackJob = useCallback((jobId) => {
    if (!isAdmin || !jobId) return;
    setActiveJobId(jobId);
    setJob(null);
  }, [isAdmin]);

  const clearJob = useCallback(() => {
    setActiveJobId(null);
    setJob(null);
  }, []);

  const startPipelineSync = useCallback((sub, options = {}) => {
    if (!isAdmin || !sub) return;
    pipelineOptionsRef.current = options;
    notifiedPipelineRef.current = null;
    setPipelineSubscription(sub);
    setPipeline(options.initialPipeline || null);
    setSyncLabel(options.label || 'Running sync pipeline');
    setSyncing(true);
  }, [isAdmin]);

  const clearPipelineSync = useCallback(() => {
    setPipelineSubscription(null);
    setPipeline(null);
    pipelineOptionsRef.current = null;
    notifiedPipelineRef.current = null;
    endSync();
  }, [endSync]);

  const cancelActiveWork = useCallback(async () => {
    if (!isAdmin || !subscription) return;
    try {
      if (pipelineSubscription && pipelineActive) {
        await cancelSyncPipeline({ subscription_id: pipelineSubscription });
        clearPipelineSync();
        showToast('Sync cancelled.', { variant: 'info' });
        return;
      }
      if (activeJobIdRef.current) {
        await cancelAnalysisJob(activeJobIdRef.current, subscription);
        clearJob();
        showToast('Analysis cancelled.', { variant: 'info' });
        return;
      }
      endSync();
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not cancel the current operation.'), { variant: 'error' });
    }
  }, [
    isAdmin,
    subscription,
    pipelineSubscription,
    pipelineActive,
    clearPipelineSync,
    clearJob,
    endSync,
    showToast,
  ]);

  const applyJobUpdate = useCallback((nextJob) => {
    applyLatestJob(setJob, setActiveJobId, activeJobIdRef.current, nextJob);
  }, []);

  const handleJobEvent = useCallback((evt) => {
    if (evt?.job) applyJobUpdate(evt.job);
  }, [applyJobUpdate]);

  const pollActiveJobs = useCallback(async () => {
    if (!isAdmin || !subscription || !subscriptionRegistered) return;
    try {
      const rows = await fetchAnalysisJobs({
        subscription_id: subscription,
        active_only: true,
        limit: 5,
      });
      rows.forEach((row) => applyLatestJob(setJob, setActiveJobId, activeJobIdRef.current, row));
      const trackedId = activeJobIdRef.current;
      if (trackedId) {
        const tracked = await fetchAnalysisJob(trackedId, subscription);
        applyLatestJob(setJob, setActiveJobId, trackedId, tracked);
      }
    } catch {
      /* polling is best-effort */
    }
  }, [isAdmin, subscription, subscriptionRegistered, applyJobUpdate]);

  const { data: pipelinePayload } = useQuery({
    queryKey: ['sync-pipeline', pipelineSubscription],
    queryFn: () => fetchSyncPipelineStatus({ subscription_id: pipelineSubscription }),
    enabled: isAdmin && Boolean(pipelineSubscription),
    refetchInterval: (q) => {
      const row = q.state.data?.pipeline;
      if (!row) return 2500;
      if (row.pending || row.status === 'queued' || row.status === 'running') return 2500;
      return false;
    },
  });

  useEffect(() => {
    if (pipelinePayload?.pipeline) {
      setPipeline(pipelinePayload.pipeline);
    }
  }, [pipelinePayload]);

  useEffect(() => {
    if (!isAdmin || !pipelineSubscription || !pipeline) return;
    if (pipeline.pending || pipeline.status === 'queued' || pipeline.status === 'running') {
      const stage = pipeline.current_stage;
      if (stage) {
        setSyncLabel(`${pipelineStageLabel(stage)}…`);
      }
      return;
    }

    const notifyKey = `${pipelineSubscription}:${pipeline.pipeline_id}:${pipeline.status}`;
    if (notifiedPipelineRef.current === notifyKey) return;
    notifiedPipelineRef.current = notifyKey;

    const options = pipelineOptionsRef.current || {};
    const runAdvisor = options.runAdvisor !== false;

    (async () => {
      let advisorResult = null;
      if (runAdvisor && pipeline.status === 'completed') {
        try {
          advisorResult = await syncAzureAdvisorRecommendations({ subscription_id: pipelineSubscription });
        } catch (advisorErr) {
          advisorResult = { error: getErrorMessage(advisorErr, 'Advisor sync failed') };
        }
      }

      const { msg, isError } = buildSyncPipelineToast(pipeline, { advisorResult });
      showToast(msg, { variant: isError ? 'error' : 'success' });

      const invalidateKeys = options.invalidateKeys || [];
      await Promise.all(
        invalidateKeys.map((key) => queryClient.invalidateQueries({ queryKey: key })),
      );
      if (runAdvisor) {
        await queryClient.invalidateQueries({ queryKey: ['advisor-index', pipelineSubscription] });
        await queryClient.invalidateQueries({ queryKey: ['dashboard-overview', pipelineSubscription] });
        await queryClient.invalidateQueries({ queryKey: ['sync-status', pipelineSubscription] });
        await queryClient.invalidateQueries({ queryKey: ['dashboard-sync', pipelineSubscription] });
        await queryClient.invalidateQueries({ queryKey: ['dashboard-sync-status', pipelineSubscription] });
      }
      await queryClient.invalidateQueries({ queryKey: ['findings-index', pipelineSubscription] });
      await queryClient.invalidateQueries({ queryKey: ['findings-summary', pipelineSubscription] });
      await queryClient.invalidateQueries({ queryKey: ['resource-counts', pipelineSubscription] });
      await queryClient.invalidateQueries({
        predicate: (q) => Array.isArray(q.queryKey)
          && typeof q.queryKey[0] === 'string'
          && q.queryKey[0].startsWith('/resources'),
      });

      if (pipeline.analysis_job_id) {
        trackJob(pipeline.analysis_job_id);
      }
      if (options.onComplete) {
        options.onComplete({ pipeline, advisor: advisorResult });
      }
      if (options.reloadSubscriptions) {
        await options.reloadSubscriptions();
      }

      clearPipelineSync();
    })();
  }, [
    pipeline,
    pipelineSubscription,
    isAdmin,
    showToast,
    queryClient,
    trackJob,
    clearPipelineSync,
  ]);

  const hasActiveWork = syncing
    || pipelineActive
    || !!activeJobId
    || job?.status === 'queued'
    || job?.status === 'running';
  const pollIntervalMs = hasActiveWork ? 10_000 : 30_000;

  const { connected: sseConnected } = useServerEvents(subscription, {
    enabled: isAdmin && !!subscription && subscriptionRegistered,
    onJobEvent: handleJobEvent,
    onPoll: pollActiveJobs,
    pollIntervalMs,
  });

  useEffect(() => {
    if (!isAdmin || !activeJobId || !subscription) return;
    fetchAnalysisJob(activeJobId, subscription)
      .then((next) => applyLatestJob(setJob, setActiveJobId, activeJobId, next))
      .catch(() => {});
  }, [activeJobId, subscription, isAdmin]);

  const { data: polledJob } = useQuery({
    queryKey: ['analysis-job', activeJobId],
    queryFn: () => fetchAnalysisJob(activeJobId, subscription),
    enabled: isAdmin && !!activeJobId && !!subscription,
    refetchInterval: (q) => {
      const st = q.state.data?.status;
      if (st !== 'queued' && st !== 'running') return false;
      return sseConnected ? 10_000 : 3_000;
    },
  });

  useEffect(() => {
    if (polledJob) applyJobUpdate(polledJob);
  }, [polledJob, applyJobUpdate]);

  useEffect(() => {
    if (!isAdmin) return;
    if (!job?.status || job.status === 'queued' || job.status === 'running') return;
    if (!subscription) {
      clearJob();
      return;
    }

    const notifyKey = `${activeJobId}:${job.status}`;
    if (notifiedJobRef.current !== notifyKey) {
      notifiedJobRef.current = notifyKey;
      if (job.status === 'completed') {
        const count = job.components?.reduce((n, c) => n + (c.findings || 0), 0) || 0;
        showToast(`Batch analysis complete — ${count.toLocaleString()} findings.`, { variant: 'success' });
      } else if (job.status === 'failed') {
        showToast(job.error_message || 'Batch analysis failed.', { variant: 'error' });
      }
    }

    queryClient.invalidateQueries({ queryKey: ['dashboard-overview', subscription] });
    queryClient.invalidateQueries({ queryKey: ['resource-counts', subscription] });
    queryClient.invalidateQueries({ queryKey: ['opt-overview', subscription] });
    queryClient.invalidateQueries({ queryKey: ['findings-index', subscription] });
    queryClient.invalidateQueries({ queryKey: ['findings-summary', subscription] });
    queryClient.invalidateQueries({ queryKey: ['optimize-actions', subscription] });
    queryClient.invalidateQueries({
      predicate: (q) => Array.isArray(q.queryKey)
        && typeof q.queryKey[0] === 'string'
        && q.queryKey[0].startsWith('/idle-resources'),
    });
    queryClient.invalidateQueries({
      predicate: (q) => Array.isArray(q.queryKey)
        && typeof q.queryKey[0] === 'string'
        && q.queryKey[0].startsWith('/resources'),
    });
    queryClient.invalidateQueries({ queryKey: ['runs', subscription] });
    const timer = setTimeout(clearJob, 1200);
    return () => clearTimeout(timer);
  }, [job?.status, job?.components, job?.error_message, subscription, clearJob, queryClient, activeJobId, showToast, isAdmin]);

  const value = useMemo(() => ({
    syncing: isAdmin && syncing,
    syncLabel: isAdmin ? syncLabel : '',
    pipeline: isAdmin ? pipeline : null,
    pipelineActive: isAdmin && pipelineActive,
    activeJobId: isAdmin ? activeJobId : null,
    job: isAdmin ? job : null,
    sseConnected: isAdmin && sseConnected,
    beginSync,
    endSync,
    trackJob,
    clearJob,
    startPipelineSync,
    clearPipelineSync,
    cancelActiveWork,
    isActive: isAdmin && (syncing || pipelineActive || !!activeJobId),
  }), [
    isAdmin,
    syncing,
    syncLabel,
    pipeline,
    pipelineActive,
    activeJobId,
    job,
    sseConnected,
    beginSync,
    endSync,
    trackJob,
    clearJob,
    startPipelineSync,
    clearPipelineSync,
    cancelActiveWork,
  ]);

  return (
    <OperationProgressCtx.Provider value={value}>
      {children}
    </OperationProgressCtx.Provider>
  );
}

export function useOperationProgress() {
  const ctx = useContext(OperationProgressCtx);
  if (!ctx) {
    throw new Error('useOperationProgress must be used within OperationProgressProvider');
  }
  return ctx;
}
