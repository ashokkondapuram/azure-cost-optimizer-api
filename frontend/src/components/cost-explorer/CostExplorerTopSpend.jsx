import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchResourceDailyCost } from '../../api/azure';
import { getResourceIconMeta } from '../../utils/ceResourceIcons';
import {
  formatIsoCurrency,
  sparklineFromCosts,
  trendClass,
  trendPctLabel,
} from '../../utils/costExplorerV2Utils';

function DetailPanel({ row, currency, subscription, costLabel, sparkTitle }) {
  const { data: dailyCost } = useQuery({
    queryKey: ['ce-resource-daily', subscription, row?.resourceId],
    queryFn: () => fetchResourceDailyCost({
      subscription_id: subscription,
      resource_id: row.resourceId,
      days: 28,
    }),
    enabled: Boolean(subscription && row?.resourceId),
    staleTime: 5 * 60_000,
  });

  const spark = useMemo(() => {
    const costs = (dailyCost?.points || []).map((p) => p.cost || 0);
    return sparklineFromCosts(costs, 240, 48);
  }, [dailyCost]);

  if (!row) {
    return (
      <aside className="ce-detail-panel" id="ce-detail-panel" aria-label="Resource cost detail">
        <p className="panel-empty">Select a resource to view cost detail.</p>
      </aside>
    );
  }

  const icon = getResourceIconMeta(row.service, row.resourceType);

  return (
    <aside className="ce-detail-panel" id="ce-detail-panel" aria-label="Resource cost detail">
      <div className="ce-detail-panel__head">
        <div className={`resource-icon ${icon.className}`} id="ce-detail-icon">{icon.label}</div>
        <div>
          <h3 className="ce-detail-panel__title" id="ce-detail-title">{row.name}</h3>
          <p className="ce-detail-panel__sub" id="ce-detail-type">
            {row.service} · {row.resourceGroup}
          </p>
        </div>
      </div>
      <div className="ce-detail-kpis">
        <div className="ce-detail-kpi">
          <span className="ce-detail-kpi__label" id="ce-detail-cost-label">{costLabel}</span>
          <strong className="ce-detail-kpi__value" id="ce-detail-mtd">
            {formatIsoCurrency(row.cost, currency)}
          </strong>
        </div>
        <div className="ce-detail-kpi">
          <span className="ce-detail-kpi__label">Prior period</span>
          <strong className="ce-detail-kpi__value" id="ce-detail-prior">
            {row.prior != null ? formatIsoCurrency(row.prior, currency) : '—'}
          </strong>
        </div>
        <div className="ce-detail-kpi">
          <span className="ce-detail-kpi__label">% of subscription</span>
          <strong className="ce-detail-kpi__value" id="ce-detail-share">
            {row.sharePct >= 0.1 ? `${row.sharePct.toFixed(1)}%` : '<0.1%'}
          </strong>
        </div>
      </div>
      <section className="ce-detail-section">
        <h4 className="ce-detail-section__title">Meter details</h4>
        <dl className="ce-detail-dl" id="ce-detail-meters">
          <div><dt>Service</dt><dd>{row.service}</dd></div>
          <div><dt>Resource type</dt><dd>{row.resourceType || '—'}</dd></div>
          <div><dt>Region</dt><dd>{row.region || '—'}</dd></div>
        </dl>
      </section>
      <section className="ce-detail-section">
        <h4 className="ce-detail-section__title">Reservation coverage</h4>
        <p className="ce-detail-text" id="ce-detail-reservation">
          {row.reservationNote || 'No reservation applied · pay-as-you-go rate'}
        </p>
      </section>
      <section className="ce-detail-section">
        <h4 className="ce-detail-section__title" id="ce-detail-spark-title">{sparkTitle}</h4>
        {spark ? (
          <svg className="ce-detail-spark" id="ce-detail-spark" viewBox="0 0 240 48" preserveAspectRatio="none" aria-hidden="true">
            <path d={spark.linePath} fill="none" stroke="#4db8ff" strokeWidth="2" strokeLinecap="round" />
          </svg>
        ) : (
          <p className="ce-detail-text">No daily trend for this resource.</p>
        )}
      </section>
    </aside>
  );
}

const SORT_COLS = {
  resource: (a, b) => a.name.localeCompare(b.name),
  service: (a, b) => a.service.localeCompare(b.service),
  rg: (a, b) => a.resourceGroup.localeCompare(b.resourceGroup),
  cost: (a, b) => b.cost - a.cost,
  prior: (a, b) => (b.prior ?? 0) - (a.prior ?? 0),
  trend: (a, b) => (b.trendPct ?? 0) - (a.trendPct ?? 0),
  share: (a, b) => b.sharePct - a.sharePct,
};

export default function CostExplorerTopSpend({
  rows,
  currency,
  subscription,
  costLabel = 'Period cost',
  anomalyResourceIds,
  loading,
  sparkTitle,
}) {
  const [sortCol, setSortCol] = useState('cost');
  const [sortDir, setSortDir] = useState('desc');
  const [selectedId, setSelectedId] = useState(null);

  const sorted = useMemo(() => {
    const sorter = SORT_COLS[sortCol] || SORT_COLS.cost;
    const copy = [...rows];
    copy.sort(sorter);
    if (sortDir === 'asc') copy.reverse();
    return copy;
  }, [rows, sortCol, sortDir]);

  const selected = sorted.find((r) => r.resourceId === selectedId) || sorted[0] || null;

  const onSort = (col) => {
    if (sortCol === col) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortCol(col);
      setSortDir(col === 'resource' || col === 'service' || col === 'rg' ? 'asc' : 'desc');
    }
  };

  if (loading) {
    return (
      <div className="ce-table-wrap">
        <div className="panel ce-table-panel" aria-busy="true" style={{ minHeight: 280 }} />
      </div>
    );
  }

  return (
    <div className="ce-table-wrap">
      <div className="panel table-panel ce-table-panel">
        <div className="panel-head panel-head--inset panel-head--split">
          <div>
            <h2 className="section-title section-title--bar">Top spend</h2>
            <p className="panel-sub" id="ce-spenders-sub">
              {sorted.length} resource{sorted.length === 1 ? '' : 's'} · sorted by highest cost
            </p>
          </div>
        </div>
        {sorted.length === 0 ? (
          <p className="ce-empty" id="ce-empty">No resources match your filters. Try clearing a filter or search term.</p>
        ) : (
          <div className="ce-table-scroll">
            <table className="ce-spenders-table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th
                    className={`ce-sortable${sortCol === 'resource' ? ` active ${sortDir}` : ''}`}
                    data-ce-sort-col="resource"
                    scope="col"
                    onClick={() => onSort('resource')}
                  >
                    Resource
                  </th>
                  <th
                    className={`ce-sortable${sortCol === 'service' ? ` active ${sortDir}` : ''}`}
                    data-ce-sort-col="service"
                    scope="col"
                    onClick={() => onSort('service')}
                  >
                    Service
                  </th>
                  <th
                    className={`ce-sortable${sortCol === 'rg' ? ` active ${sortDir}` : ''}`}
                    data-ce-sort-col="rg"
                    scope="col"
                    onClick={() => onSort('rg')}
                  >
                    Resource group
                  </th>
                  <th
                    className={`ce-sortable${sortCol === 'cost' ? ` active ${sortDir}` : ''}`}
                    data-ce-sort-col="cost"
                    scope="col"
                    id="ce-cost-col-header"
                    onClick={() => onSort('cost')}
                  >
                    {costLabel}
                  </th>
                  <th
                    className={`ce-sortable${sortCol === 'prior' ? ` active ${sortDir}` : ''}`}
                    data-ce-sort-col="prior"
                    scope="col"
                    onClick={() => onSort('prior')}
                  >
                    Prior period
                  </th>
                  <th
                    className={`ce-sortable${sortCol === 'trend' ? ` active ${sortDir}` : ''}`}
                    data-ce-sort-col="trend"
                    scope="col"
                    onClick={() => onSort('trend')}
                  >
                    Change %
                  </th>
                  <th
                    className={`ce-sortable${sortCol === 'share' ? ` active ${sortDir}` : ''}`}
                    data-ce-sort-col="share"
                    scope="col"
                    onClick={() => onSort('share')}
                  >
                    % of total
                  </th>
                </tr>
              </thead>
              <tbody id="ce-spenders-rows">
                {sorted.map((row, index) => {
                  const icon = getResourceIconMeta(row.service, row.resourceType);
                  return (
                    <tr
                      key={row.resourceId}
                      className={selected?.resourceId === row.resourceId ? 'selected' : ''}
                      tabIndex={0}
                      onClick={() => setSelectedId(row.resourceId)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelectedId(row.resourceId);
                        }
                      }}
                    >
                      <td className="ce-rank">{index + 1}</td>
                      <td>
                        <div className="resource-cell">
                          <div className={`resource-icon ${icon.className}`}>{icon.label}</div>
                          <div className="resource-cell__body">
                            <strong>{row.name}</strong>
                          </div>
                        </div>
                      </td>
                      <td>{row.service}</td>
                      <td>{row.resourceGroup}</td>
                      <td className="cost-cell">{formatIsoCurrency(row.cost, currency)}</td>
                      <td className="cost-cell cost-cell--muted">
                        {row.prior != null ? formatIsoCurrency(row.prior, currency) : '—'}
                      </td>
                      <td>
                        <span className={`ce-trend ${trendClass(row.trendPct)}`}>
                          {trendPctLabel(row.trendPct)}
                        </span>
                      </td>
                      <td>{row.sharePct >= 0.1 ? `${row.sharePct.toFixed(1)}%` : '<0.1%'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <DetailPanel
        row={selected}
        currency={currency}
        subscription={subscription}
        costLabel={costLabel}
        sparkTitle={sparkTitle}
      />
    </div>
  );
}
