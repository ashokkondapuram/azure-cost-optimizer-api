import api from './client';

// Subscriptions
export const fetchSubscriptions  = ()         => api.get('/resources/subscriptions').then(r => r.data);

// Costs
export const fetchCosts          = (p)        => api.get('/costs', { params: p }).then(r => r.data);
export const fetchCostByResource = (p)        => api.get('/costs/by-resource', { params: p }).then(r => r.data);
export const fetchCostByService  = (p)        => api.get('/costs/by-service', { params: p }).then(r => r.data);
export const fetchForecast       = (p)        => api.get('/costs/forecast', { params: p }).then(r => r.data);
export const fetchBudgets        = (p)        => api.get('/costs/budgets', { params: p }).then(r => r.data);

// Resources
export const fetchVMs            = (p)        => api.get('/resources/vms', { params: p }).then(r => r.data);
export const fetchDisks          = (p)        => api.get('/resources/disks', { params: p }).then(r => r.data);
export const fetchAKS            = (p)        => api.get('/resources/aks', { params: p }).then(r => r.data);
export const fetchStorage        = (p)        => api.get('/resources/storage', { params: p }).then(r => r.data);
export const fetchPublicIPs      = (p)        => api.get('/resources/publicips', { params: p }).then(r => r.data);
export const fetchSQL            = (p)        => api.get('/resources/sql', { params: p }).then(r => r.data);
export const fetchKeyVaults      = (p)        => api.get('/resources/keyvaults', { params: p }).then(r => r.data);
export const fetchResourceGroups = (p)        => api.get('/resources/resource-groups', { params: p }).then(r => r.data);
export const fetchVMSkus         = (p)        => api.get('/resources/vm-skus', { params: p }).then(r => r.data);

// Optimization
export const runAnalysis         = (body)     => api.post('/optimize/analyze', body).then(r => r.data);
export const fetchRuns           = (p)        => api.get('/optimize/runs', { params: p }).then(r => r.data);
export const fetchRun            = (id)       => api.get(`/optimize/runs/${id}`).then(r => r.data);
export const fetchFindings       = (p)        => api.get('/optimize/findings', { params: p }).then(r => r.data);
export const fetchFindingsSummary = (p)       => api.get('/optimize/findings/summary', { params: p }).then(r => r.data);
export const updateFindingStatus = (id, s)    => api.patch(`/optimize/findings/${id}/status`, { status: s }).then(r => r.data);
export const fetchRules          = ()         => api.get('/optimize/rules').then(r => r.data);
export const fetchProfiles       = ()         => api.get('/optimize/config').then(r => r.data);
export const fetchProfileConfig  = (prof)     => api.get(`/optimize/config/${prof}`).then(r => r.data);
export const upsertProfileConfig = (prof, b)  => api.post(`/optimize/config/${prof}`, b).then(r => r.data);
export const deleteProfileConfig = (prof, id) => api.delete(`/optimize/config/${prof}/${id}`).then(r => r.data);
