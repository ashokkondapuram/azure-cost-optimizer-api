import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { fetchAksPoolInstances } from '../../../api/azure';
import { formatCpu } from '../../../utils/formatMetricUnits';
import { formatPowerState } from '../../../utils/formatDisplay';
import { normalizePoolInstance } from '../utils/aksPoolUtilization';
import AksPoolVmssLink from './AksPoolVmssLink';

function utilizationTitle(source, scope = 'pool') {
  if (scope === 'instance') {
    if (source === 'k8s_agent') return 'Per-instance metric from K8s agent';
    if (source === 'azure_monitor') return 'Per-instance metric from Azure Monitor';
    return 'Per-instance CPU and memory';
  }
  if (source === 'cluster') return 'Cluster-wide average';
  if (source === 'node') return 'Pool average from node metrics';
  if (source === 'vmss') return 'Pool average from VM scale set metrics';
  if (source === 'k8s_agent') return 'K8s agent metric';
  if (source === 'azure_monitor') return 'Azure Monitor metric';
  return scope === 'pool' ? 'Pool average' : undefined;
}

function UtilizationCell({ value, source, scope = 'pool' }) {
  if (value == null) {
    return <span className="insight-drawer__muted">—</span>;
  }
  return (
    <span title={utilizationTitle(source, scope)}>
      {formatCpu(value)}
    </span>
  );
}

function PoolUsageSummary({ pool }) {
  const nodeLabel = pool.autoscaleRange ?? pool.count ?? 0;
  return (
    <div className="aks-pool-usage">
      <span>{nodeLabel} nodes</span>
      <span className="aks-pool-usage__sep" aria-hidden>·</span>
      <span>
        Pool CPU{' '}
        <UtilizationCell value={pool.cpuPct} source={pool.utilizationSource} scope="pool" />
      </span>
      <span className="aks-pool-usage__sep" aria-hidden>·</span>
      <span>
        Pool memory{' '}
        <UtilizationCell value={pool.memPct} source={pool.utilizationSource} scope="pool" />
      </span>
    </div>
  );
}

function poolInstancesEmptyMessage(pool, { loading = false, loadError = false } = {}) {
  if (loading) return 'Loading VMSS instances…';
  if (loadError) return 'Could not load VMSS instances. Try again.';
  if (pool?._vmssId || pool?.vmssId) {
    return 'No VMSS instances synced yet. Run inventory sync or expand again to load from Azure.';
  }
  return 'VM scale set not linked yet. Run inventory sync to attach node pool VMSS references.';
}

function InstanceRows({ instances = [], pool, loading = false, loadError = false }) {
  if (!instances.length) {
    return (
      <tr className="aks-pool-instances__empty-row">
        <td colSpan={9}>
          <span className="insight-drawer__muted">
            {poolInstancesEmptyMessage(pool, { loading, loadError })}
          </span>
        </td>
      </tr>
    );
  }

  return instances.map((instance) => (
    <tr key={instance.id || instance.instanceId || instance.name} className="aks-pool-instances__row">
      <td />
      <td colSpan={5} className="aks-pool-instances__name-cell">
        <div className="aks-pool-instances__name insight-drawer__mono">{instance.name}</div>
        {instance.instanceId != null && (
          <div className="aks-pool-instances__id insight-drawer__muted">
            ID {instance.instanceId}
          </div>
        )}
      </td>
      <td>{formatPowerState(instance.powerState) || '—'}</td>
      <td>
        <UtilizationCell value={instance.cpuPct} source={instance.metricsSource} scope="instance" />
      </td>
      <td>
        <UtilizationCell value={instance.memPct} source={instance.metricsSource} scope="instance" />
      </td>
    </tr>
  ));
}

export default function AksNodePoolsTable({
  pools = [],
  compact = false,
  resourceId = null,
  subscriptionId = null,
  timespan = 'P7D',
  emptyMessage = 'No node pool data synced yet. Run inventory sync to load agent pool profiles.',
}) {
  const [expanded, setExpanded] = useState(() => new Set());
  const [loadedInstances, setLoadedInstances] = useState({});
  const [loadingPools, setLoadingPools] = useState(() => new Set());
  const [loadErrors, setLoadErrors] = useState(() => new Set());

  const poolsWithInstances = useMemo(
    () => (pools || []).map((pool) => ({
      ...pool,
      instances: loadedInstances[pool.name] ?? pool.instances ?? [],
    })),
    [pools, loadedInstances],
  );

  const loadPoolInstances = useCallback(async (poolName, { force = false } = {}) => {
    if (!resourceId || !subscriptionId || !poolName) return;
    if (!force && (loadedInstances[poolName]?.length || loadingPools.has(poolName))) return;

    setLoadingPools((prev) => new Set(prev).add(poolName));
    setLoadErrors((prev) => {
      const next = new Set(prev);
      next.delete(poolName);
      return next;
    });

    try {
      const payload = await fetchAksPoolInstances({
        subscription_id: subscriptionId,
        resource_id: resourceId,
        pool: poolName,
        timespan,
      });
      const raw = payload?.pools?.[poolName] || [];
      setLoadedInstances((prev) => ({
        ...prev,
        [poolName]: raw.map(normalizePoolInstance),
      }));
    } catch {
      setLoadErrors((prev) => new Set(prev).add(poolName));
    } finally {
      setLoadingPools((prev) => {
        const next = new Set(prev);
        next.delete(poolName);
        return next;
      });
    }
  }, [loadedInstances, loadingPools, resourceId, subscriptionId, timespan]);

  useEffect(() => {
    setExpanded(new Set());
  }, [resourceId, subscriptionId]);

  useEffect(() => {
    setLoadedInstances({});
    setLoadingPools(new Set());
    setLoadErrors(new Set());
  }, [resourceId, subscriptionId, timespan]);

  useEffect(() => {
    if (!expanded.size) return;
    for (const poolName of expanded) {
      loadPoolInstances(poolName, { force: true });
    }
  }, [timespan]); // eslint-disable-line react-hooks/exhaustive-deps

  const togglePool = useCallback((poolName) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      const opening = !next.has(poolName);
      if (opening) {
        next.add(poolName);
        const pool = poolsWithInstances.find((row) => row.name === poolName);
        if (pool && !(pool.instances || []).length) {
          loadPoolInstances(poolName);
        }
      } else {
        next.delete(poolName);
      }
      return next;
    });
  }, [loadPoolInstances, poolsWithInstances]);

  if (!poolsWithInstances.length) {
    return (
      <p className="insight-drawer__empty insight-drawer__empty--compact">{emptyMessage}</p>
    );
  }

  if (compact) {
    return (
      <div className="aks-pool-list aks-pool-list--compact">
        {poolsWithInstances.map((pool) => {
          const isOpen = expanded.has(pool.name);
          const canExpand = Boolean(
            (pool.instances || []).length
            || pool._vmssId
            || pool.vmssId,
          );
          const isLoading = loadingPools.has(pool.name);
          const loadError = loadErrors.has(pool.name);
          return (
            <div key={pool.name} className="aks-pool-list__item">
              <div className="aks-pool-list__header">
                <button
                  type="button"
                  className="aks-pool-expand-btn"
                  onClick={() => togglePool(pool.name)}
                  aria-expanded={isOpen}
                  aria-label={`${isOpen ? 'Collapse' : 'Expand'} ${pool.name} instances`}
                  disabled={!canExpand}
                >
                  <ChevronDown
                    size={14}
                    className={`aks-pool-expand-btn__chevron${isOpen ? ' aks-pool-expand-btn__chevron--open' : ''}`}
                    aria-hidden
                  />
                  <span className="aks-pool-list__name">{pool.name}</span>
                </button>
                <span className="insight-drawer__mono aks-pool-list__size">{pool.vmSize || '—'}</span>
              </div>
              <div className="aks-pool-list__vmss">
                <span className="aks-pool-list__label">VM scale set</span>
                <AksPoolVmssLink vmssId={pool._vmssId || pool.vmssId} vmssName={pool._vmssName || pool.vmssName} />
              </div>
              <PoolUsageSummary pool={pool} />
              {isOpen && (
                <div className="aks-pool-instances aks-pool-instances--compact">
                  {(pool.instances || []).map((instance) => (
                    <div key={instance.id || instance.instanceId || instance.name} className="aks-pool-instances__item">
                      <span className="insight-drawer__mono">{instance.name}</span>
                      <span className="aks-pool-instances__meta">
                        CPU <UtilizationCell value={instance.cpuPct} source={instance.metricsSource} scope="instance" />
                        <span className="aks-pool-usage__sep" aria-hidden>·</span>
                        Memory <UtilizationCell value={instance.memPct} source={instance.metricsSource} scope="instance" />
                        <span className="aks-pool-usage__sep" aria-hidden>·</span>
                        {formatPowerState(instance.powerState) || '—'}
                      </span>
                    </div>
                  ))}
                  {!pool.instances?.length && (
                    <span className="insight-drawer__muted">
                      {poolInstancesEmptyMessage(pool, { loading: isLoading, loadError })}
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="table-wrap insight-drawer__table-wrap">
      <table className="insight-drawer__table aks-pool-table">
        <thead>
          <tr>
            <th aria-label="Expand" />
            <th>Pool</th>
            <th>Mode</th>
            <th>Nodes</th>
            <th>VM size</th>
            <th>VM scale set</th>
            <th>Autoscale</th>
            <th>Pool CPU</th>
            <th>Pool memory</th>
          </tr>
        </thead>
        <tbody>
          {poolsWithInstances.map((pool) => {
            const isOpen = expanded.has(pool.name);
            const canExpand = Boolean(
              (pool.instances || []).length
              || pool._vmssId
              || pool.vmssId,
            );
            const isLoading = loadingPools.has(pool.name);
            const loadError = loadErrors.has(pool.name);
            return (
              <React.Fragment key={pool.name}>
                <tr className="aks-pool-table__pool-row">
                  <td className="aks-pool-table__expand-cell">
                    <button
                      type="button"
                      className="aks-pool-expand-btn aks-pool-expand-btn--table"
                      onClick={() => togglePool(pool.name)}
                      aria-expanded={isOpen}
                      aria-label={`${isOpen ? 'Collapse' : 'Expand'} ${pool.name} instances`}
                      disabled={!canExpand}
                    >
                      <ChevronDown
                        size={14}
                        className={`aks-pool-expand-btn__chevron${isOpen ? ' aks-pool-expand-btn__chevron--open' : ''}`}
                        aria-hidden
                      />
                    </button>
                  </td>
                  <td>
                    <div className="aks-pool-list__name">{pool.name}</div>
                  </td>
                  <td>{pool.mode || '—'}</td>
                  <td>{pool.autoscaleRange ?? pool.count ?? 0}</td>
                  <td className="insight-drawer__mono">{pool.vmSize || '—'}</td>
                  <td className="aks-pool-list__vmss">
                    <AksPoolVmssLink
                      vmssId={pool._vmssId || pool.vmssId}
                      vmssName={pool._vmssName || pool.vmssName}
                    />
                  </td>
                  <td>{pool.enableAutoScaling ? 'On' : 'Off'}</td>
                  <td>
                    <UtilizationCell value={pool.cpuPct} source={pool.utilizationSource} scope="pool" />
                  </td>
                  <td>
                    <UtilizationCell value={pool.memPct} source={pool.utilizationSource} scope="pool" />
                  </td>
                </tr>
                {isOpen && (
                  <InstanceRows
                    instances={pool.instances}
                    pool={pool}
                    loading={isLoading}
                    loadError={loadError}
                  />
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
