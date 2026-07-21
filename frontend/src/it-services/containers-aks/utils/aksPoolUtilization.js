/** Match K8s node metric keys to AKS agent pool names (mirrors app/optimizer/engine.py). */

function buildPoolPrefixes(clusterName, pools = []) {
  const cname = String(clusterName || '').toLowerCase();
  return (pools || [])
    .filter((pool) => pool?.name)
    .map((pool) => ({
      name: pool.name,
      prefix: `${cname}-${String(pool.name).toLowerCase()}`,
      poolNameLower: String(pool.name).toLowerCase(),
      clusterName: cname,
    }));
}

export function matchNodeToPool(nodeKey, clusterName, poolPrefixes = []) {
  const nodeLower = String(nodeKey || '').toLowerCase();
  if (!nodeLower) return null;

  let clusterHint = '';
  let nodeName = nodeLower;
  if (nodeLower.includes('/')) {
    [clusterHint, nodeName] = nodeLower.split('/', 2);
  }

  const cname = String(clusterName || '').toLowerCase();
  for (const entry of poolPrefixes) {
    if (clusterHint && entry.clusterName !== clusterHint) continue;
    if (nodeName.includes(entry.prefix) || nodeLower.includes(entry.prefix)) {
      return entry.name;
    }
    const token = `aks-${entry.poolNameLower}`;
    if (nodeName.includes(token)) {
      return entry.name;
    }
  }
  return null;
}

function finiteNumber(value) {
  if (value == null || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

export function extractInstanceUtilization(instance) {
  const detail = instance?.metrics_detail || instance?.metrics || [];
  let cpu = null;
  let mem = null;
  for (const row of detail) {
    const key = row?.fact_key;
    const val = row?.stats?.average ?? row?.stats?.maximum ?? row?.value;
    if (key === 'node_cpu_pct' || key === 'avg_cpu_pct') cpu = finiteNumber(val);
    if (key === 'node_mem_pct' || key === 'avg_memory_pct') mem = finiteNumber(val);
  }
  if (cpu == null && instance?.cpu_pct != null) cpu = finiteNumber(instance.cpu_pct);
  if (mem == null && instance?.mem_pct != null) mem = finiteNumber(instance.mem_pct);
  return { cpu, mem };
}

export function normalizePoolInstance(row = {}) {
  const { cpu, mem } = extractInstanceUtilization(row);
  return {
    id: row.id || row.resource_id || null,
    name: row.name || row.computer_name || row.instance_id || '—',
    instanceId: row.instance_id ?? row.instanceId ?? null,
    powerState: row.power_state || row.powerState || null,
    cpuPct: cpu,
    memPct: mem,
    metricsSource: row.source || null,
  };
}

/**
 * Attach VMSS instance rows from backend pool_metrics or synced pool inventory.
 */
export function attachPoolInstances(pools = [], poolMetrics = []) {
  const instancesByPool = new Map(
    (poolMetrics || [])
      .filter((row) => row?.name)
      .map((row) => [row.name, row.vmss_instances || []]),
  );

  return (pools || []).map((pool) => {
    const backendInstances = instancesByPool.get(pool.name) || [];
    const syncedInstances = pool.vmssInstances || [];
    const raw = backendInstances.length ? backendInstances : syncedInstances;
    const instances = raw.map(normalizePoolInstance);
    return {
      ...pool,
      instances,
      instanceCount: instances.length || pool.count || 0,
    };
  });
}

function average(values = []) {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

/**
 * Enrich synced node pools with CPU/memory utilization from node instances or cluster facts.
 * @param {string} clusterName
 * @param {Array} pools - normalized pools from agentPoolProfiles
 * @param {Array} instances - metrics API instances (k8s_agent nodes)
 * @param {Object} clusterFacts - cluster-level facts (cluster_cpu_pct, cluster_mem_pct)
 * @param {Array} poolMetrics - optional backend pool_metrics rows
 */
export function aggregatePoolUtilization(
  clusterName,
  pools = [],
  instances = [],
  clusterFacts = {},
  poolMetrics = [],
) {
  if (!pools?.length) return [];

  const metricsByPool = new Map(
    (poolMetrics || [])
      .filter((row) => row?.name)
      .map((row) => [row.name, row]),
  );

  const poolPrefixes = buildPoolPrefixes(clusterName, pools);
  const buckets = new Map(
    pools.map((pool) => [pool.name, { cpus: [], mems: [], nodesWithMetrics: 0 }]),
  );

  for (const instance of instances || []) {
    const key = instance?.name || instance?.instance_id || '';
    const poolName = instance?.pool_name || matchNodeToPool(key, clusterName, poolPrefixes);
    if (!poolName || !buckets.has(poolName)) continue;
    const { cpu, mem } = extractInstanceUtilization(instance);
    const bucket = buckets.get(poolName);
    if (cpu != null) bucket.cpus.push(cpu);
    if (mem != null) bucket.mems.push(mem);
    if (cpu != null || mem != null) bucket.nodesWithMetrics += 1;
  }

  const hasPerPoolMetrics = [...buckets.values()].some((bucket) => bucket.nodesWithMetrics > 0);
  const clusterCpu = finiteNumber(clusterFacts.cluster_cpu_pct);
  const clusterMem = finiteNumber(clusterFacts.cluster_mem_pct);

  return pools.map((pool) => {
    const bucket = buckets.get(pool.name) || { cpus: [], mems: [], nodesWithMetrics: 0 };
    const backend = metricsByPool.get(pool.name);
    let cpuPct = backend?.cpu_pct ?? average(bucket.cpus);
    let memPct = backend?.mem_pct ?? average(bucket.mems);
    let utilizationSource = backend?.source
      || (bucket.nodesWithMetrics > 0 ? 'node' : null);

    if (cpuPct == null && !hasPerPoolMetrics && clusterCpu != null) {
      cpuPct = clusterCpu;
      utilizationSource = utilizationSource || 'cluster';
    }
    if (memPct == null && !hasPerPoolMetrics && clusterMem != null) {
      memPct = clusterMem;
      utilizationSource = utilizationSource || 'cluster';
    }

    const vmssInstanceCount = backend?.vmss_instance_count;
    const nodeCount = vmssInstanceCount ?? pool.count ?? null;

    return {
      ...pool,
      cpuPct,
      memPct,
      nodesWithMetrics: backend?.nodes_with_metrics ?? bucket.nodesWithMetrics,
      utilizationSource,
      vmssId: pool.vmssId || backend?.vmss_id || pool._vmssId,
      count: nodeCount ?? pool.count,
    };
  });
}
