import api from './client';
import { getStoredToken } from './tokenStorage';
import { coerceMetricTimespan } from '../utils/metricsTimespanUtils';
import {
  ANALYZE_ACCEPT_TIMEOUT_MS,
  SYNC_ACCEPT_TIMEOUT_MS,
  isAnalyzeAcceptResponse,
  isSyncAcceptResponse,
  isTimeoutError,
  normalizeAnalyzeJobPayload,
  normalizeSyncAcceptPayload,
} from '../utils/asyncAcceptUtils';
import {
  CANONICAL_NESTED_PATHS,
  CANONICAL_TO_API_PATH,
} from '../config/resourceApiPaths';

export { SYNC_ACCEPT_TIMEOUT_MS, ANALYZE_ACCEPT_TIMEOUT_MS };

function withSyncAcceptParams(params = {}) {
  return { ...params, wait: false };
}

async function recoverSyncAcceptAfterTimeout(subscriptionId) {
  if (!subscriptionId) return null;
  try {
    const status = await fetchSyncPipelineStatus({ subscription_id: subscriptionId });
    const pipeline = status?.pipeline;
    if (
      pipeline?.pending
      || pipeline?.status === 'queued'
      || pipeline?.status === 'running'
    ) {
      return normalizeSyncAcceptPayload(
        {
          ...status,
          async: true,
          pending: true,
          status: 'accepted',
          pipeline,
          recovered: true,
        },
        202,
      );
    }
  } catch {
    /* recovery poll is best-effort */
  }
  return null;
}

async function recoverAnalyzeAcceptAfterTimeout(subscriptionId) {
  if (!subscriptionId) return null;
  try {
    const rows = await fetchAnalysisJobs({
      subscription_id: subscriptionId,
      active_only: true,
      limit: 1,
    });
    const job = normalizeAnalyzeJobPayload(rows?.[0]);
    if (job && isAnalyzeAcceptResponse(job)) {
      return { ...job, recovered: true };
    }
  } catch {
    /* recovery poll is best-effort */
  }
  return null;
}

async function postSyncAccept(path, params) {
  try {
    const response = await api.post(path, null, {
      params: withSyncAcceptParams(params),
      timeout: SYNC_ACCEPT_TIMEOUT_MS,
      validateStatus: (status) => status === 200 || status === 202,
    });
    const payload = normalizeSyncAcceptPayload(response.data, response.status);
    if (isSyncAcceptResponse(payload, response.status)) {
      return payload;
    }
    return { ...payload, httpStatus: response.status };
  } catch (error) {
    if (!isTimeoutError(error)) throw error;
    const recovered = await recoverSyncAcceptAfterTimeout(params?.subscription_id);
    if (recovered) return recovered;
    throw error;
  }
}

async function postAnalyzeAccept(path, body) {
  try {
    const response = await api.post(path, body, {
      timeout: ANALYZE_ACCEPT_TIMEOUT_MS,
      validateStatus: (status) => status >= 200 && status < 300,
    });
    const payload = normalizeAnalyzeJobPayload(response.data);
    if (isAnalyzeAcceptResponse(payload)) {
      return payload;
    }
    return payload;
  } catch (error) {
    if (!isTimeoutError(error)) throw error;
    const recovered = await recoverAnalyzeAcceptAfterTimeout(body?.subscription_id);
    if (recovered) return recovered;
    throw error;
  }
}

function withMetricTimespan(value) {
  if (value == null || typeof value !== 'object') return value;
  if (!('timespan' in value)) return value;
  return { ...value, timespan: coerceMetricTimespan(value.timespan) };
}

/** Normalize list responses from Azure ARM or DB-backed endpoints. */
export function normalizeListResponse(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.value)) return data.value;
  if (Array.isArray(data?.items)) return data.items;
  if (Array.isArray(data?.subscriptions)) return data.subscriptions;
  return [];
}

/** Paginated list envelope from DB-backed endpoints when limit is set. */
export function normalizePagedResponse(data) {
  if (data && Array.isArray(data.items) && typeof data.total === 'number') {
    return {
      items: data.items,
      total: data.total,
      limit: data.limit,
      offset: data.offset,
      page_count: data.page_count,
      has_more: Boolean(data.has_more),
      next_cursor: data.next_cursor || null,
    };
  }
  const items = normalizeListResponse(data);
  return {
    items,
    total: items.length,
    limit: items.length,
    offset: 0,
    has_more: false,
  };
}

export function normalizeSubscription(sub) {
  const rawId = sub?.subscriptionId || sub?.subscription_id || sub?.id || '';
  const parsed = String(rawId).includes('/')
    ? String(rawId).replace(/\/+$/, '').split('/').pop()
    : String(rawId);
  const id = parsed.trim().toLowerCase();
  return {
    subscriptionId: id,
    displayName: sub?.displayName || sub?.display_name || id,
    state: sub?.state || 'Unknown',
    tenantId: sub?.tenantId || sub?.tenant_id || null,
  };
}

export function normalizeSubscriptions(data) {
  return normalizeListResponse(data)
    .map(normalizeSubscription)
    .filter((s) => s.subscriptionId);
}

export function parseSubscriptionsResponse(data) {
  const defaultSubscriptionId = (
    data?.default_subscription_id || data?.defaultSubscriptionId || ''
  ).trim().toLowerCase();
  const subscriptions = normalizeSubscriptions(data?.subscriptions ?? data);
  return { subscriptions, defaultSubscriptionId: defaultSubscriptionId || null };
}

// Subscriptions
export const fetchSubscriptions = () =>
  api.get('/resources/subscriptions').then((r) => parseSubscriptionsResponse(r.data));

export const syncSubscriptions = () =>
  api.post('/resources/subscriptions/sync').then((r) => {
    const payload = r.data?.subscriptions != null ? r.data : { subscriptions: r.data };
    return parseSubscriptionsResponse(payload);
  });

export const validateSubscriptionAccess = (body) =>
  api.post('/resources/subscriptions/validate', body).then((r) => r.data);

export const addSubscription = (body) =>
  api.post('/resources/subscriptions', body).then((r) => parseSubscriptionsResponse(r.data));

// Costs
export const fetchCosts = (p) => api.get('/costs', { params: p }).then((r) => r.data);
export const fetchCostTimeframes = () => api.get('/costs/timeframes').then((r) => r.data);
export const fetchCostSummary = (p) => api.get('/costs/summary', { params: p }).then((r) => r.data);
export const fetchCostChanges = (p) => api.get('/costs/changes', { params: p }).then((r) => r.data);
export const fetchCostByResource = (p) => api.get('/costs/by-resource', { params: p }).then((r) => r.data);
export const fetchResourceDailyCost = (p, options = {}) =>
  api.get('/costs/resource-daily', { params: p, ...options }).then((r) => r.data);
export const fetchUtilizationSeries = (p, options = {}) =>
  api.get('/metrics/utilization-series', { params: withMetricTimespan(p), ...options }).then((r) => r.data);
export const fetchCostByService = (p) => api.get('/costs/by-service', { params: p }).then((r) => r.data);
export const fetchResourceTypes = () => api.get('/resource-types').then((r) => r.data);
export const fetchForecast = (p) => api.get('/costs/forecast', { params: p }).then((r) => r.data);
export const fetchBudgets = (p) => api.get('/budgets', { params: p }).then((r) => {
  const data = r.data;
  if (Array.isArray(data)) return data;
  return data?.budgets || [];
});

// Dashboard (DB-backed, spec-aligned)
export const fetchDashboardOverview = (p) =>
  api.get('/dashboard/overview', { params: p, timeout: 60_000 })
    .then((r) => r.data);
export const fetchDashboardSyncStatus = (p) => api.get('/sync/status', { params: p }).then((r) => r.data);
export const fetchDashboardTopSpend = (p) => api.get('/cost/topspend', { params: p }).then((r) => r.data);
export const fetchDashboardUnderutil = (p) => api.get('/outliers/underutil', { params: p }).then((r) => r.data);
export const fetchDashboardAlerts = (p) => api.get('/alerts', { params: p }).then((r) => r.data);
export const fetchDashboardAdvisor = (p) => api.get('/advisor', { params: p }).then((r) => r.data);
export const fetchResourceDetail = (p) => api.get('/resources/detail', { params: p }).then((r) => r.data);

export const fetchResourceAzureMetrics = (p) =>
  api.get('/metrics/resource/auto', { params: withMetricTimespan(p) }).then((r) => r.data);

export const fetchMetricsProfiles = () =>
  api.get('/metrics/profiles').then((r) => r.data);

export const fetchMetricsTriggers = () =>
  api.get('/metrics/triggers').then((r) => r.data);

export const fetchResourceCostMapping = (p) =>
  api.get('/metrics/resource-cost-mapping', { params: p }).then((r) => r.data);

export const syncCosts = (p) => postSyncAccept('/costs/sync', p);

export const triggerFullSync = (p) => postSyncAccept('/sync/full', p);

export const fetchSyncPipelineStatus = (p) =>
  api.get('/sync/pipeline', { params: p, timeout: 30_000 }).then((r) => r.data);

export const fetchSyncProgress = (p) =>
  api.get('/sync/progress', { params: p, timeout: 30_000 }).then((r) => r.data);

/** EventSource URL for GET /sync/progress/stream (dashboard SSE). */
export function buildSyncProgressStreamUrl({ subscription_id: subscriptionId } = {}) {
  const params = new URLSearchParams();
  if (subscriptionId) params.set('subscription_id', subscriptionId);
  const token = getStoredToken();
  if (token) params.set('access_token', token);
  const qs = params.toString();
  return `/api/sync/progress/stream${qs ? `?${qs}` : ''}`;
}

export const cancelSyncPipeline = (p) =>
  api.post('/sync/pipeline/cancel', null, {
    params: p,
    timeout: SYNC_ACCEPT_TIMEOUT_MS,
  }).then((r) => r.data);

export const resetSyncPipeline = (p) =>
  api.post('/sync/reset', null, {
    params: p,
    timeout: SYNC_ACCEPT_TIMEOUT_MS,
  }).then((r) => r.data);

// Resources
export const DEFAULT_SYNC_PAGE_SIZE = 50;

export const syncResources = (p) => postSyncAccept('/resources/sync', p);
export const fetchVMs = (p) => api.get(CANONICAL_TO_API_PATH['compute/vm'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchVmSizing = (p) =>
  api.get(CANONICAL_NESTED_PATHS.vmSizing(p.resource_group, p.vm_name), {
    params: withMetricTimespan({
      subscription_id: p.subscription_id,
      timespan: p.timespan || 'P7D',
    }),
  }).then((r) => r.data);
export const persistVmSizingOpenFinding = (p) =>
  api.post(
    CANONICAL_NESTED_PATHS.vmSizingOpenFinding(p.resource_group, p.vm_name),
    null,
    {
      params: withMetricTimespan({
        subscription_id: p.subscription_id,
        timespan: p.timespan || 'P7D',
      }),
    },
  ).then((r) => r.data);
export const fetchDisks = (p) => api.get(CANONICAL_TO_API_PATH['compute/disk'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchAKS = (p) => api.get(CANONICAL_TO_API_PATH['containers/aks'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchK8sSnapshots = (p = {}) => api.get('/k8s/snapshots', { params: p }).then((r) => r.data);
export const fetchK8sSnapshot = (p = {}) => api.get('/k8s/snapshot', { params: p }).then((r) => r.data);
export const fetchAksKubernetesVersions = (p) =>
  api.get(CANONICAL_NESTED_PATHS.aksKubernetesVersions, { params: p }).then((r) => r.data);
export const fetchAksPoolInstances = (p) =>
  api.get(CANONICAL_NESTED_PATHS.aksPoolInstances, {
    params: withMetricTimespan({
      subscription_id: p.subscription_id,
      resource_id: p.resource_id,
      pool: p.pool,
      timespan: p.timespan || 'P7D',
    }),
  }).then((r) => r.data);
export const fetchStorage = (p) => api.get(CANONICAL_TO_API_PATH['storage/account'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchPublicIPs = (p) => api.get(CANONICAL_TO_API_PATH['network/publicip'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchSQL = (p) => api.get(CANONICAL_TO_API_PATH['database/sql'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchKeyVaults = (p) => api.get(CANONICAL_TO_API_PATH['security/keyvault'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchResourceGroups = (p) => api.get('/resources/resource-groups', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchResourceCounts = (subscriptionId) =>
  api.get('/resources/counts', { params: { subscription_id: subscriptionId } }).then((r) => r.data);
export const fetchVMSkus = (p) => api.get('/resources/vm-skus', { params: p }).then((r) => r.data);
export const fetchAppServices = (p) => api.get(CANONICAL_TO_API_PATH['appservice/webapp'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchLoadBalancers = (p) => api.get(CANONICAL_TO_API_PATH['network/loadbalancer'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchAppGateways = (p) => api.get(CANONICAL_TO_API_PATH['network/appgateway'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchNsgs = (p) => api.get(CANONICAL_TO_API_PATH['network/nsg'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchAcr = (p) => api.get(CANONICAL_TO_API_PATH['containers/acr'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchCosmosDb = (p) => api.get(CANONICAL_TO_API_PATH['database/cosmosdb'], { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchPostgresql = (p) => api.get(CANONICAL_TO_API_PATH['database/postgresql'], { params: p }).then((r) => normalizeListResponse(r.data));

export function fetchResources(apiPath, params) {
  return api.get(apiPath, { params }).then((r) => {
    if (params?.limit != null) {
      return normalizePagedResponse(r.data);
    }
    return normalizeListResponse(r.data);
  });
}

export const fetchBilledResourceProperties = (p) =>
  api.get('/resources/billed/properties', {
    params: {
      subscription_id: p.subscription_id,
      resource_id: p.resource_id,
    },
  }).then((r) => r.data);

// Optimization
export const runAnalysis = (body) => postAnalyzeAccept('/optimize/analyze', body);
export const analyzeResource = (body) =>
  api.post('/optimize/resources/analyze', body).then((r) => r.data);
export const fetchRuns = (p) => api.get('/optimize/runs', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchRun = (id, subscriptionId) =>
  api.get(`/optimize/runs/${id}`, { params: { subscription_id: subscriptionId } }).then((r) => r.data);
export const fetchFindings = (p) => api.get('/optimize/findings', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchFindingsPage = (p) => api.get('/optimize/findings', { params: p }).then((r) => normalizePagedResponse(r.data));
export const fetchFindingsSummary = (p) => api.get('/optimize/findings/summary', { params: p }).then((r) => r.data);
export const updateFindingStatus = (id, status, subscriptionId) =>
  api.patch(`/optimize/findings/${id}/status`, { status }, {
    params: { subscription_id: subscriptionId },
  }).then((r) => r.data);
export const bulkUpdateFindingStatus = (findingIds, status, subscriptionId) =>
  api.patch('/optimize/findings/bulk-status', { finding_ids: findingIds, status }, {
    params: { subscription_id: subscriptionId },
  }).then((r) => r.data);
export const fetchRules = () => api.get('/optimize/rules').then((r) => r.data);
export const fetchRulesByComponent = () => api.get('/optimize/rules/by-component').then((r) => r.data);
export const fetchProfiles = () => api.get('/optimize/config').then((r) => r.data);
export const fetchProfileConfig = (prof) => api.get(`/optimize/config/${prof}`).then((r) => r.data);
export const fetchCompareProfiles = (profiles = 'default,aggressive,conservative') =>
  api.get('/optimize/config/compare', { params: { profiles } }).then((r) => r.data);
export const fetchGlobalConfigDefaults = () =>
  api.get('/optimize/config/global/defaults').then((r) => r.data);
export const validateProfileConfig = (profile, draftOverrides = {}) =>
  api.post(`/optimize/config/${profile}/validate`, { draft_overrides: draftOverrides }).then((r) => r.data);
export const upsertProfileConfig = (prof, b) => api.post(`/optimize/config/${prof}`, b).then((r) => r.data);
export const deleteProfileConfig = (prof, id) => api.delete(`/optimize/config/${prof}/${id}`).then((r) => r.data);
export const reanalyzeAfterRuleConfig = (prof, engineVersion = 'extended') =>
  api.post(`/optimize/config/${prof}/reanalyze`, null, { params: { engine_version: engineVersion } }).then((r) => r.data);

// Admin optimization
export const fetchOptimizationOverview = (p) =>
  api.get('/admin/optimization/overview', { params: p }).then((r) => r.data);
export const startBatchAnalysis = (body) => postAnalyzeAccept('/optimize/analyze/batch', body);
export const fetchAnalysisJob = (id, subscriptionId) =>
  api.get(`/optimize/jobs/${id}`, { params: { subscription_id: subscriptionId } }).then((r) => r.data);
export const fetchAnalysisJobs = (p) => api.get('/optimize/jobs', { params: p }).then((r) => normalizeListResponse(r.data));
export const cancelAnalysisJob = (jobId, subscriptionId) =>
  api.post(`/optimize/jobs/${jobId}/cancel`, null, { params: { subscription_id: subscriptionId } }).then((r) => r.data);

export const fetchFindingActivity = (findingId, subscriptionId) =>
  api.get(`/optimize/findings/${findingId}/activity`, { params: { subscription_id: subscriptionId } }).then((r) => r.data);

export const logFindingExecution = (findingId, body, subscriptionId) =>
  api.post(`/optimize/findings/${findingId}/execute`, body, {
    params: { subscription_id: subscriptionId },
  }).then((r) => r.data);

// Azure Advisor (Microsoft.Advisor snapshots)
export const fetchAzureAdvisorRecommendations = (p) =>
  api.get('/optimize/advisor/list', { params: p }).then((r) => r.data);
export const syncAzureAdvisorRecommendations = (p) =>
  api.post('/optimize/advisor/sync', null, { params: p, timeout: 300_000 }).then((r) => r.data);
export const generateAzureAdvisorRecommendations = (p) =>
  api.post('/optimize/advisor/generate', null, { params: p, timeout: 300_000 }).then((r) => r.data);

// Optimization actions (decision engine + workflow)
export const fetchOptimizationActions = (p) =>
  api.get('/optimize/actions/list', { params: p }).then((r) => r.data);
export const decideOptimizationActions = (p) =>
  api.post('/optimize/actions/decide', null, { params: p, timeout: 300_000 }).then((r) => r.data);
export const updateOptimizationAction = (actionId, body, subscriptionId) =>
  api.patch(`/optimize/actions/${actionId}`, body, {
    params: { subscription_id: subscriptionId },
  }).then((r) => r.data);
export const bulkUpdateOptimizationActions = (body, subscriptionId) =>
  api.patch('/optimize/actions/bulk-status', body, {
    params: { subscription_id: subscriptionId },
  }).then((r) => r.data);
export const bulkAssignOptimizationActions = (body, subscriptionId) =>
  api.patch('/optimize/actions/bulk-assign', body, {
    params: { subscription_id: subscriptionId },
  }).then((r) => r.data);

// Advanced optimization engine
export const fetchOptimizationTrends = (p) =>
  api.get('/optimize/trends', { params: p }).then((r) => r.data);
export const fetchResourceAdvancedAnalysis = (p) =>
  api.get('/optimize/resources/analysis', { params: p }).then((r) => r.data);

export const fetchBatchResourceLookup = (body, config = {}) =>
  api.post('/optimize/resources/batch-lookup', withMetricTimespan(body), config).then((r) => r.data);

export const validateFindingExecution = (findingId, body, subscriptionId) =>
  api.post(`/optimize/findings/${findingId}/validate`, body, {
    params: { subscription_id: subscriptionId },
  }).then((r) => r.data);

export const patchResourceTags = ({ subscription_id, resource_id, tags }) => {
  const rid = (resource_id || '').startsWith('/') ? resource_id : `/${resource_id}`;
  return api.patch(`/resources${rid}/tags`, { tags }, {
    params: { subscription_id },
  }).then((r) => r.data);
};

export const bulkPatchResourceTags = (body) =>
  api.patch('/resources/bulk-tags', body).then((r) => r.data);

/** Poll unified sync pipeline until completed or failed. */
export async function pollSyncPipeline(subscriptionId, { intervalMs = 2500, timeoutMs = 900000, onProgress } = {}) {
  const started = Date.now();
  let sawPipeline = false;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const payload = await fetchSyncPipelineStatus({ subscription_id: subscriptionId });
    const pipeline = payload?.pipeline;
    if (pipeline) {
      sawPipeline = true;
      if (onProgress) onProgress(pipeline);
    }
    if (!pipeline?.pending) {
      if (pipeline?.status === 'failed') {
        throw new Error(pipeline.error || 'Sync pipeline failed.');
      }
      if (!pipeline) {
        if (sawPipeline) {
          throw new Error('Sync pipeline ended without a final status. Retry sync or check server logs.');
        }
        if (Date.now() - started > timeoutMs) {
          throw new Error(
            'Sync pipeline status was not available. If you use microservices, confirm /sync/pipeline routes to the inventory service.',
          );
        }
      } else {
        return pipeline;
      }
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error('Sync is still running. Check sync status for progress.');
    }
    await new Promise((resolve) => { setTimeout(resolve, intervalMs); });
  }
}

/** Poll a background analysis job until completed or failed. */
export async function pollAnalysisJob(jobId, subscriptionId, { intervalMs = 2000, timeoutMs = 900000 } = {}) {
  const started = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const job = await fetchAnalysisJob(jobId, subscriptionId);
    if (job.status === 'completed') {
      return job;
    }
    if (job.status === 'failed') {
      throw new Error(job.error_message || 'Analysis failed.');
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error('Analysis is still running. Check Sync center for progress.');
    }
    await new Promise((resolve) => { setTimeout(resolve, intervalMs); });
  }
}

export const clearDatabaseData = (params = {}) =>
  api.post('/admin/data/clear', null, { params }).then((r) => r.data);
