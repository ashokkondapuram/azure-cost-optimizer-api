import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  buildSyncProgressStreamUrl,
  fetchSyncPipelineStatus,
  fetchSyncProgress,
} from '../api/azure';
import { useOperationProgress } from '../context/OperationProgressContext';
import { useAuth } from '../context/AuthContext';
import {
  isPipelineActive,
  normalizeSyncProgressEntry,
  pickSyncProgressEntry,
  resolvePipelineUiStatus,
  resolveSyncProgressLabel,
  resolveSyncRetryHint,
} from '../utils/syncPipelineUtils';

const POLL_MS = 2500;
const TERMINAL_DISPLAY_MS = 6000;

function parseSseData(raw) {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function isProgressApiUnavailable(error) {
  const status = error?.response?.status;
  return status === 404 || status === 405;
}

/**
 * Dashboard sync progress: prefer SSE GET /sync/progress/stream, poll GET /sync/progress
 * every 2.5s when SSE is down, and fall back to legacy GET /sync/pipeline on 404.
 */
export default function useSyncProgress(subscriptionId, { enabled = true } = {}) {
  const { isAdmin } = useAuth();
  const {
    syncing,
    pipeline: contextPipeline,
    pipelineActive,
    pipelineSubscription,
  } = useOperationProgress();

  const contextMatches = pipelineSubscription === subscriptionId;
  const optimisticSyncing = syncing && (!pipelineSubscription || contextMatches);

  const [useLegacyPipeline, setUseLegacyPipeline] = useState(false);
  const [sseConnected, setSseConnected] = useState(false);
  const [streamPipeline, setStreamPipeline] = useState(null);

  const progressApiEnabled = isAdmin && enabled && Boolean(subscriptionId) && !useLegacyPipeline;

  const applyProgressPayload = useCallback((payload) => {
    const entry = pickSyncProgressEntry(payload, subscriptionId);
    if (entry) {
      setStreamPipeline(normalizeSyncProgressEntry(entry));
    }
  }, [subscriptionId]);

  const handleSseEvent = useCallback((evt) => {
    if (!evt) return;
    if (evt.type === 'snapshot') {
      applyProgressPayload(evt);
      return;
    }
    if (evt.type === 'progress' && evt.progress) {
      const sub = (evt.progress.subscription_id || '').toLowerCase();
      const target = (subscriptionId || '').toLowerCase();
      if (!target || sub === target) {
        setStreamPipeline(normalizeSyncProgressEntry(evt.progress));
      }
    }
  }, [applyProgressPayload, subscriptionId]);

  const handleSseEventRef = useRef(handleSseEvent);
  handleSseEventRef.current = handleSseEvent;

  useEffect(() => {
    if (!progressApiEnabled) {
      setSseConnected(false);
      return undefined;
    }

    let cancelled = false;
    const source = new EventSource(buildSyncProgressStreamUrl({ subscription_id: subscriptionId }));

    source.onopen = () => {
      if (!cancelled) setSseConnected(true);
    };
    source.onmessage = (message) => {
      if (cancelled) return;
      setSseConnected(true);
      handleSseEventRef.current(parseSseData(message.data));
    };
    source.onerror = () => {
      if (!cancelled) setSseConnected(false);
    };

    return () => {
      cancelled = true;
      source.close();
      setSseConnected(false);
    };
  }, [subscriptionId, progressApiEnabled]);

  const { data: progressPayload } = useQuery({
    queryKey: ['sync-progress', subscriptionId],
    queryFn: async () => {
      try {
        return await fetchSyncProgress({ subscription_id: subscriptionId });
      } catch (error) {
        if (isProgressApiUnavailable(error)) {
          setUseLegacyPipeline(true);
        }
        throw error;
      }
    },
    enabled: progressApiEnabled,
    refetchInterval: (query) => {
      if (sseConnected) return false;
      const entry = pickSyncProgressEntry(query.state.data, subscriptionId);
      const pipeline = normalizeSyncProgressEntry(entry);
      const active = isPipelineActive(pipeline)
        || optimisticSyncing
        || (contextMatches && pipelineActive);
      if (active) return POLL_MS;
      return false;
    },
    staleTime: 0,
    retry: (failureCount, error) => !isProgressApiUnavailable(error) && failureCount < 2,
  });

  const { data: legacyPayload } = useQuery({
    queryKey: ['sync-pipeline-progress', subscriptionId],
    queryFn: () => fetchSyncPipelineStatus({ subscription_id: subscriptionId }),
    enabled: isAdmin && enabled && Boolean(subscriptionId) && useLegacyPipeline,
    refetchInterval: (query) => {
      const row = query.state.data?.pipeline;
      const active = isPipelineActive(row)
        || optimisticSyncing
        || (contextMatches && pipelineActive);
      if (active) return POLL_MS;
      return false;
    },
    staleTime: 0,
  });

  const polledPipeline = useMemo(() => {
    if (useLegacyPipeline) return legacyPayload?.pipeline ?? null;
    if (streamPipeline) return streamPipeline;
    const entry = pickSyncProgressEntry(progressPayload, subscriptionId);
    return normalizeSyncProgressEntry(entry);
  }, [useLegacyPipeline, legacyPayload, streamPipeline, progressPayload, subscriptionId]);

  const polledActive = isPipelineActive(polledPipeline);

  const pipeline = useMemo(() => {
    if (contextMatches && contextPipeline) {
      if (!polledPipeline) return contextPipeline;
      if (polledPipeline.pipeline_id === contextPipeline.pipeline_id) return polledPipeline;
      if (isPipelineActive(contextPipeline) && !isPipelineActive(polledPipeline)) {
        return contextPipeline;
      }
    }
    return polledPipeline || (contextMatches ? contextPipeline : null);
  }, [contextMatches, contextPipeline, polledPipeline]);

  const uiStatus = resolvePipelineUiStatus(pipeline, { syncing: optimisticSyncing });
  const progressPct = pipeline?.percent_complete
    ?? pipeline?.progress_pct
    ?? (optimisticSyncing ? 0 : 0);
  const label = resolveSyncProgressLabel(pipeline, { syncing: optimisticSyncing, uiStatus });
  const retryHint = resolveSyncRetryHint(pipeline);
  const isActive = uiStatus === 'running'
    || optimisticSyncing
    || (contextMatches && pipelineActive)
    || polledActive;

  const [showTerminal, setShowTerminal] = useState(false);
  const terminalTimerRef = useRef(null);

  useEffect(() => {
    if (uiStatus === 'completed' || uiStatus === 'failed') {
      setShowTerminal(true);
      if (terminalTimerRef.current) clearTimeout(terminalTimerRef.current);
      terminalTimerRef.current = setTimeout(() => setShowTerminal(false), TERMINAL_DISPLAY_MS);
      return () => {
        if (terminalTimerRef.current) clearTimeout(terminalTimerRef.current);
      };
    }
    setShowTerminal(false);
    return undefined;
  }, [uiStatus, pipeline?.pipeline_id]);

  const visible = isActive || showTerminal;

  return {
    pipeline,
    uiStatus,
    progressPct,
    label,
    retryHint,
    isActive,
    visible,
    sseConnected,
    currentStage: pipeline?.current_stage ?? null,
    stages: pipeline?.stage_statuses ?? pipeline?.stages ?? null,
  };
}
