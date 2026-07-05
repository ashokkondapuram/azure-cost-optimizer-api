import React, {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchAnalysisJob, fetchAnalysisJobs } from '../api/azure';
import useServerEvents from '../hooks/useServerEvents';
import { useToast } from './ToastContext';
import { useAuth } from './AuthContext';

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

export function OperationProgressProvider({ children, subscription }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { isAdmin } = useAuth();
  const notifiedJobRef = useRef(null);
  const activeJobIdRef = useRef(null);
  const [syncing, setSyncing] = useState(false);
  const [syncLabel, setSyncLabel] = useState('');
  const [activeJobId, setActiveJobId] = useState(null);
  const [job, setJob] = useState(null);

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

  const applyJobUpdate = useCallback((nextJob) => {
    applyLatestJob(setJob, setActiveJobId, activeJobIdRef.current, nextJob);
  }, []);

  const handleJobEvent = useCallback((evt) => {
    if (evt?.job) applyJobUpdate(evt.job);
  }, [applyJobUpdate]);

  const pollActiveJobs = useCallback(async () => {
    if (!isAdmin || !subscription) return;
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
  }, [isAdmin, subscription, applyJobUpdate]);

  const { connected: sseConnected } = useServerEvents(subscription, {
    enabled: isAdmin && !!subscription,
    onJobEvent: handleJobEvent,
    onPoll: pollActiveJobs,
    pollIntervalMs: 10_000,
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
    queryClient.invalidateQueries({ queryKey: ['findings', subscription] });
    queryClient.invalidateQueries({ queryKey: ['findings-summary', subscription] });
    queryClient.invalidateQueries({ queryKey: ['findings-index', subscription] });
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
    activeJobId: isAdmin ? activeJobId : null,
    job: isAdmin ? job : null,
    sseConnected: isAdmin && sseConnected,
    beginSync,
    endSync,
    trackJob,
    clearJob,
    isActive: isAdmin && (syncing || !!activeJobId),
  }), [isAdmin, syncing, syncLabel, activeJobId, job, sseConnected, beginSync, endSync, trackJob, clearJob]);

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
