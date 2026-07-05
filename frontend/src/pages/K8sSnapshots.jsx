import React, { useContext, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { fetchK8sSnapshot, fetchK8sSnapshots } from '../api/azure';
import PageHeader from '../components/PageHeader';
import PageHero from '../components/layout/PageHero';
import OptimizationHubLinks from '../components/navigation/OptimizationHubLinks';
import { PAGE_ICONS } from '../config/assetIcons';
import { LoadingState, SubscriptionRequired, EmptyState, QueryErrorState } from '../components/QueryStates';
import { formatDateTime } from '../utils/format';

export default function K8sSnapshots() {
  const { subscription } = useContext(AppCtx);
  const [selectedCluster, setSelectedCluster] = useState('');

  const {
    data: snapshots = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['k8s-snapshots', subscription],
    queryFn: () => fetchK8sSnapshots(),
    enabled: !!subscription,
    staleTime: 60_000,
  });

  const clusterNames = useMemo(
    () => [...new Set(snapshots.map((s) => s.cluster_name).filter(Boolean))].sort(),
    [snapshots],
  );

  const activeCluster = selectedCluster || clusterNames[0] || '';

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['k8s-snapshot', activeCluster],
    queryFn: () => fetchK8sSnapshot({ cluster_name: activeCluster }),
    enabled: !!activeCluster,
    staleTime: 60_000,
  });

  const payload = detail?.snapshot || {};
  const nodes = payload.nodes || [];
  const pods = payload.pods || [];

  return (
    <div className="page-shell k8s-snapshots-page">
      <PageHeader
        title="Cluster utilization"
        iconKey={PAGE_ICONS.kubernetes}
        subtitle={subscription ? 'Recent snapshots from the utilization agent' : 'Select a subscription'}
      />

      {subscription && snapshots.length > 0 && (
        <PageHero
          variant="k8s-hero"
          eyebrow="Kubernetes"
          title={activeCluster || 'Cluster utilization'}
          subtitle={`${clusterNames.length} cluster${clusterNames.length === 1 ? '' : 's'} reporting · ${snapshots.length} snapshot${snapshots.length === 1 ? '' : 's'}`}
          isLoading={isLoading}
          metrics={[
            { label: 'Nodes', value: (detail?.node_count ?? nodes.length).toLocaleString(), tone: 'default' },
            { label: 'Pods', value: (detail?.pod_count ?? pods.length).toLocaleString(), tone: 'default' },
            {
              label: 'Last snapshot',
              value: detail?.recorded_at ? formatDateTime(detail.recorded_at).split(' at ')[0] : '—',
              tone: 'default',
            },
          ]}
        actions={[
          { id: 'settings', label: 'Kubernetes agent', href: '/settings' },
          { id: 'aks', label: 'AKS clusters', href: '/aks' },
        ]}
        />
      )}

      <OptimizationHubLinks className="optimization-hub--page" />

      {!subscription && <SubscriptionRequired />}

      {subscription && isLoading && <LoadingState message="Loading cluster snapshots…" />}
      {subscription && isError && <QueryErrorState error={error} onRetry={refetch} />}

      {subscription && !isLoading && !isError && snapshots.length === 0 && (
        <EmptyState
          iconKey={PAGE_ICONS.kubernetes}
          message="No cluster snapshots yet. Configure the utilization agent to push data to this app."
        />
      )}

      {subscription && !isLoading && !isError && snapshots.length > 0 && (
        <>
          <section className="page-section card k8s-cluster-picker">
            <label htmlFor="k8s-cluster-select" className="topbar-label">Cluster</label>
            <select
              id="k8s-cluster-select"
              className="select-field"
              value={activeCluster}
              onChange={(e) => setSelectedCluster(e.target.value)}
            >
              {clusterNames.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </section>

          {detailLoading && <LoadingState message="Loading snapshot detail…" />}

          {!detailLoading && nodes.length > 0 && (
            <section className="page-section card">
              <div className="card-header"><h2>Nodes</h2></div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Name</th><th>CPU</th><th>Memory</th><th>Ready</th></tr>
                  </thead>
                  <tbody>
                    {nodes.map((node) => (
                      <tr key={node.name || node.node_name}>
                        <td>{node.name || node.node_name}</td>
                        <td>{node.cpu_usage || node.cpu || '—'}</td>
                        <td>{node.memory_usage || node.memory || '—'}</td>
                        <td>{node.ready ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {!detailLoading && pods.length > 0 && (
            <section className="page-section card">
              <div className="card-header"><h2>Pods</h2></div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Name</th><th>Namespace</th><th>Node</th><th>CPU</th><th>Memory</th></tr>
                  </thead>
                  <tbody>
                    {pods.slice(0, 200).map((pod) => (
                      <tr key={`${pod.namespace}-${pod.name}`}>
                        <td>{pod.name}</td>
                        <td>{pod.namespace || '—'}</td>
                        <td>{pod.node_name || pod.node || '—'}</td>
                        <td>{pod.cpu_usage || pod.cpu || '—'}</td>
                        <td>{pod.memory_usage || pod.memory || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {pods.length > 200 && (
                <p className="text-muted" style={{ padding: '0.75rem 1rem' }}>
                  Showing first 200 of {pods.length.toLocaleString()} pods.
                </p>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
