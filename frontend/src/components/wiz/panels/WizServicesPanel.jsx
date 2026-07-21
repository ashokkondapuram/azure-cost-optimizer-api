import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';
import { fetchPipelineServices } from '../../../api/pipeline';
import { RESOURCE_PAGES } from '../../../config/appRegistry';
import AssetIcon from '../../AssetIcon';
import { LoadingState, QueryErrorState } from '../../QueryStates';

function servicePagePath(service) {
  if (!service) return null;
  const byId = RESOURCE_PAGES[service.service_id];
  if (byId?.path) return byId.path;
  const pkgKey = (service.package || '').replace(/_/g, '');
  const byPkg = Object.values(RESOURCE_PAGES).find(
    (p) => p.id === service.package || p.id === pkgKey,
  );
  return byPkg?.path || null;
}

export default function WizServicesPanel() {
  const [q, setQ] = useState('');
  const [engineOnly, setEngineOnly] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['pipeline-services'],
    queryFn: fetchPipelineServices,
    staleTime: 10 * 60_000,
  });

  const services = data?.services || [];

  const filtered = useMemo(() => {
    let list = services;
    if (engineOnly) list = list.filter((s) => s.has_engine);
    if (q.trim()) {
      const hay = q.trim().toLowerCase();
      list = list.filter((s) => {
        const text = `${s.service_id} ${s.package} ${s.canonical_type} ${s.arm_type}`.toLowerCase();
        return text.includes(hay);
      });
    }
    return list;
  }, [services, q, engineOnly]);

  if (isLoading) return <LoadingState message="Loading service catalog…" />;
  if (isError) return <QueryErrorState error={error} onRetry={refetch} />;

  return (
    <div className="wiz-panel" id="wiz-panel-services" role="tabpanel" aria-labelledby="wiz-tab-services">
      <section className="wiz-card">
        <header className="wiz-card__head">
          <h3>IT services</h3>
          <span className="wiz-pill">{filtered.length} of {services.length}</span>
        </header>
        <div className="wiz-toolbar">
          <span className="wiz-search" style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Search size={14} style={{ position: 'absolute', left: 10, opacity: 0.5 }} />
            <input
              type="search"
              placeholder="Search services…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ paddingLeft: 30, width: '100%', maxWidth: 320 }}
              aria-label="Search services"
            />
          </span>
          <label className="wiz-pill" style={{ cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={engineOnly}
              onChange={(e) => setEngineOnly(e.target.checked)}
              style={{ marginRight: 6 }}
            />
            Engines only
          </label>
        </div>

        <div className="wiz-service-grid">
          {filtered.map((svc) => {
            const path = servicePagePath(svc);
            const CardTag = path ? Link : 'div';
            const cardProps = path ? { to: path, style: { textDecoration: 'none', color: 'inherit' } } : {};
            return (
              <CardTag key={svc.service_id} className="wiz-service-card" {...cardProps}>
                <div className="wiz-service-card__head">
                  <AssetIcon iconKey={svc.package?.replace(/_/g, '-') || 'default'} size={22} />
                  <div>
                    <div className="wiz-service-card__title">{svc.service_id}</div>
                    <div className="wiz-service-card__type">{svc.canonical_type}</div>
                  </div>
                </div>
                <div className="wiz-pill-row">
                  {svc.has_engine ? (
                    <span className="wiz-pill wiz-pill--ok">Engine</span>
                  ) : (
                    <span className="wiz-pill wiz-pill--muted">No engine</span>
                  )}
                  {svc.assessment_file && (
                    <span className="wiz-pill">Assessment</span>
                  )}
                  {svc.sub_engine_class && (
                    <span className="wiz-pill wiz-pill--muted" title={svc.sub_engine_class}>Sub-engine</span>
                  )}
                </div>
                <div className="wiz-service-card__type" style={{ marginTop: 4 }}>
                  {(svc.arm_type || '').split('/').pop()}
                </div>
              </CardTag>
            );
          })}
          {filtered.length === 0 && (
            <div className="wiz-empty" style={{ gridColumn: '1 / -1' }}>
              <strong>No services match</strong>
              Adjust your search or filters.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
