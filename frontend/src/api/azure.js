import api from './client';

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

// Subscriptions
export const fetchSubscriptions = () =>
  api.get('/resources/subscriptions').then((r) => normalizeSubscriptions(r.data));

export const syncSubscriptions = () =>
  api.post('/resources/subscriptions/sync').then((r) => normalizeSubscriptions(r.data?.subscriptions || r.data));

// Costs
export const fetchCosts = (p) => api.get('/costs', { params: p }).then((r) => r.data);
export const fetchCostTimeframes = () => api.get('/costs/timeframes').then((r) => r.data);
export const fetchCostSummary = (p) => api.get('/costs/summary', { params: p }).then((r) => r.data);
export const fetchCostChanges = (p) => api.get('/costs/changes', { params: p }).then((r) => r.data);
export const fetchCostByResource = (p) => api.get('/costs/by-resource', { params: p }).then((r) => r.data);
export const fetchCostByService = (p) => api.get('/costs/by-service', { params: p }).then((r) => r.data);
export const fetchResourceTypes = () => api.get('/resource-types').then((r) => r.data);
export const fetchForecast = (p) => api.get('/costs/forecast', { params: p }).then((r) => r.data);
export const fetchBudgets = (p) => api.get('/costs/budgets', { params: p }).then((r) => r.data);

// Dashboard (DB-backed, spec-aligned)
export const fetchDashboardOverview = (p) => api.get('/dashboard/overview', { params: p }).then((r) => r.data);
export const fetchDashboardSyncStatus = (p) => api.get('/sync/status', { params: p }).then((r) => r.data);
export const fetchDashboardTopSpend = (p) => api.get('/cost/topspend', { params: p }).then((r) => r.data);
export const fetchDashboardUnderutil = (p) => api.get('/outliers/underutil', { params: p }).then((r) => r.data);
export const fetchDashboardAlerts = (p) => api.get('/alerts', { params: p }).then((r) => r.data);
export const fetchDashboardAdvisor = (p) => api.get('/advisor', { params: p }).then((r) => r.data);
export const fetchResourceDetail = (p) => api.get('/resources/detail', { params: p }).then((r) => r.data);

export const fetchResourceAzureMetrics = (p) =>
  api.get('/metrics/resource/auto', { params: p }).then((r) => r.data);

export const fetchMetricsProfiles = () =>
  api.get('/metrics/profiles').then((r) => r.data);

export const fetchMetricsTriggers = () =>
  api.get('/metrics/triggers').then((r) => r.data);

export const fetchResourceCostMapping = (p) =>
  api.get('/metrics/resource-cost-mapping', { params: p }).then((r) => r.data);

export const syncCosts = (p) =>
  api.post('/costs/sync', null, {
    params: p,
    timeout: 30_000,
    validateStatus: (status) => status === 200 || status === 202,
  }).then((r) => ({ ...r.data, httpStatus: r.status }));

// Resources
export const DEFAULT_SYNC_PAGE_SIZE = 50;

export const syncResources = (p) =>
  api.post('/resources/sync', null, {
    params: p,
    timeout: 300_000,
  }).then((r) => r.data);
export const fetchVMs = (p) => api.get('/resources/vms', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchVmSizing = (p) =>
  api.get(`/resources/vms/${encodeURIComponent(p.resource_group)}/${encodeURIComponent(p.vm_name)}/sizing`, {
    params: { subscription_id: p.subscription_id, timespan: p.timespan || 'P7D' },
  }).then((r) => r.data);
export const persistVmSizingOpenFinding = (p) =>
  api.post(
    `/resources/vms/${encodeURIComponent(p.resource_group)}/${encodeURIComponent(p.vm_name)}/sizing/open-finding`,
    null,
    { params: { subscription_id: p.subscription_id, timespan: p.timespan || 'P7D' } },
  ).then((r) => r.data);
export const fetchDisks = (p) => api.get('/resources/disks', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchAKS = (p) => api.get('/resources/aks', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchK8sSnapshots = (p = {}) => api.get('/k8s/snapshots', { params: p }).then((r) => r.data);
export const fetchK8sSnapshot = (p = {}) => api.get('/k8s/snapshot', { params: p }).then((r) => r.data);
export const fetchAksKubernetesVersions = (p) =>
  api.get('/resources/aks/kubernetes-versions', { params: p }).then((r) => r.data);
export const fetchStorage = (p) => api.get('/resources/storage', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchPublicIPs = (p) => api.get('/resources/publicips', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchSQL = (p) => api.get('/resources/sql', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchKeyVaults = (p) => api.get('/resources/keyvaults', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchResourceGroups = (p) => api.get('/resources/resource-groups', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchResourceCounts = (subscriptionId) =>
  api.get('/resources/counts', { params: { subscription_id: subscriptionId } }).then((r) => r.data);
export const fetchVMSkus = (p) => api.get('/resources/vm-skus', { params: p }).then((r) => r.data);
export const fetchAppServices = (p) => api.get('/resources/appservices', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchLoadBalancers = (p) => api.get('/resources/loadbalancers', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchAppGateways = (p) => api.get('/resources/appgateways', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchNsgs = (p) => api.get('/resources/nsgs', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchAcr = (p) => api.get('/resources/acr', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchCosmosDb = (p) => api.get('/resources/cosmosdb', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchPostgresql = (p) => api.get('/resources/postgresql', { params: p }).then((r) => normalizeListResponse(r.data));

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
export const runAnalysis = (body) => api.post('/optimize/analyze', body).then((r) => r.data);
export const fetchRuns = (p) => api.get('/optimize/runs', { params: p }).then((r) => normalizeListResponse(r.data));
export const fetchRun = (id, subscriptionId) =>
  api.get(`/optimize/runs/${id}`, { params: { subscription_id: subscriptionId } }).then((r) => r.data);
export const fetchFindings = (p) => api.get('/optimize/findings', { params: p }).then((r) => normalizeListResponse(r.data));
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
export const startBatchAnalysis = (body) =>
  api.post('/optimize/analyze/batch', body).then((r) => r.data);
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
export const runAdvancedEngineScore = (p) =>
  api.post('/optimize/engine/score', null, { params: p, timeout: 300_000 }).then((r) => r.data);
export const fetchOptimizationScoreboard = (p) =>
  api.get('/optimize/engine/scoreboard', { params: p }).then((r) => r.data);
export const planOptimizationRollout = (p) =>
  api.post('/optimize/rollout/plan', null, { params: p }).then((r) => r.data);
export const fetchRolloutStages = (p) =>
  api.get('/optimize/rollout/stages', { params: p }).then((r) => r.data);
export const startRolloutStage = (stageId, subscriptionId) =>
  api.post(`/optimize/rollout/stages/${stageId}/start`, null, {
    params: { subscription_id: subscriptionId },
  }).then((r) => r.data);
export const expandRolloutStage = (stageId, subscriptionId, force = false) =>
  api.post(`/optimize/rollout/stages/${stageId}/expand`, null, {
    params: { subscription_id: subscriptionId, force },
  }).then((r) => r.data);
export const rollbackRolloutStage = (stageId, subscriptionId, reason) =>
  api.post(`/optimize/rollout/stages/${stageId}/rollback`, null, {
    params: { subscription_id: subscriptionId, reason },
  }).then((r) => r.data);
export const observeRolloutStages = (p) =>
  api.post('/optimize/rollout/observe', null, { params: p }).then((r) => r.data);
export const fetchOptimizationTrends = (p) =>
  api.get('/optimize/trends', { params: p }).then((r) => r.data);
export const fetchResourceAdvancedAnalysis = (p) =>
  api.get('/optimize/resources/analysis', { params: p }).then((r) => r.data);

export const fetchBatchResourceLookup = (body, config = {}) =>
  api.post('/optimize/resources/batch-lookup', body, config).then((r) => r.data);

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
      throw new Error('Analysis is still running. Check Optimization center for progress.');
    }
    await new Promise((resolve) => { setTimeout(resolve, intervalMs); });
  }
}

export const clearDatabaseData = (params = {}) =>
  api.post('/admin/data/clear', null, { params }).then((r) => r.data);
