/**
 * Reservation Advisor — Azure live reservations + Advisor + engine findings.
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  AlertTriangle, ChevronDown, ChevronUp,
  Shield, X,
} from 'lucide-react';
import { fetchReservationAdvisor, syncReservationAdvisor } from '../api/reservationAdvisor';
import AdvancedToolLayout, { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';
import FilterBar from '../components/FilterBar';
import {
  AdvSkeleton,
  AdvSyncButton,
  AdvFilterChips,
  AdvHighlightPanel,
  AdvEmptyState,
  fmtCurrency,
} from '../components/advanced/AdvUI';
import { AdvHeroFooter } from '../components/advanced/AdvancedToolHero';

const COMMITMENT_BADGE = {
  reserved_instance: 'ai-tier-badge ai-tier-badge--low',
  savings_plan: 'ai-tier-badge ai-tier-badge--medium',
};
const SOURCE_LABEL = {
  azure_advisor: 'Azure Advisor',
  engine_finding: 'Engine finding',
  azure_capacity: 'Azure RI',
  azure_billing_benefits: 'Savings plan',
};

function RecRow({ rec, currency, active, onSelect }) {
  const [open, setOpen] = useState(false);
  const ct = rec.commitment_type || 'reserved_instance';
  return (
    <div className={`anomaly-alert anomaly-alert--${rec.severity === 'high' ? 'high' : 'medium'}${active ? ' anomaly-alert--active' : ''}`}>
      <div
        className="anomaly-alert__row"
        role="button"
        tabIndex={0}
        onClick={() => onSelect(rec.id)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(rec.id); } }}
      >
        <div className="anomaly-alert__meta min-w-0 flex-1">
          <span className={COMMITMENT_BADGE[ct] || 'chip'}>{ct.replace('_', ' ')}</span>
          <span className="chip">{SOURCE_LABEL[rec.source] || rec.source}</span>
          <span className="anomaly-alert__date truncate">{rec.title}</span>
        </div>
        <div className="anomaly-alert__stats">
          <span className="anomaly-alert__cost">{fmtCurrency(rec.estimated_annual_savings, currency)}/yr</span>
          <button type="button" className="text-gray-400" onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}>
            {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>
      {open && (
        <div className="anomaly-alert__detail" style={{ gridTemplateColumns: '1fr' }}>
          {rec.detail && <p className="text-sm text-gray-600 m-0">{rec.detail}</p>}
          {rec.recommendation && <p className="text-sm text-teal-700 m-0">{rec.recommendation}</p>}
          {rec.resource_id && <p className="tag-rg-table__mono m-0 truncate" title={rec.resource_id}>{rec.resource_id}</p>}
        </div>
      )}
    </div>
  );
}

function CommitmentTable({ items, currency, selectedId, onSelect }) {
  if (!items?.length) {
    return <div className="tag-rg-explorer__empty">No active reservations or savings plans returned from Azure.</div>;
  }
  return (
    <div className="tag-rg-explorer__scroll">
      <table className="tag-rg-table">
        <thead>
          <tr>
            {['Name', 'Type', 'Term', 'Utilization'].map((h) => <th key={h}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr
              key={c.id}
              className={`tag-rg-table__row${selectedId === c.id ? ' tag-rg-table__row--active' : ''}`}
              onClick={() => onSelect(c.id)}
              role="button"
              tabIndex={0}
            >
              <td className="tag-rg-table__name" title={c.display_name}>{c.display_name}</td>
              <td><span className={COMMITMENT_BADGE[c.commitment_type] || 'chip'}>{c.commitment_type?.replace('_', ' ')}</span></td>
              <td className="tag-rg-table__count">{c.term || '—'}</td>
              <td className="tag-rg-table__count">
                {c.utilization_percent != null ? `${c.utilization_percent}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ReservationAdvisor() {
  const { subscription } = useAdvancedSubscription();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState(null);
  const [commitmentType, setCommitmentType] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedRecId, setSelectedRecId] = useState('');
  const [selectedCommitmentId, setSelectedCommitmentId] = useState('');
  const [hideWarnings, setHideWarnings] = useState(false);

  const load = useCallback(async () => {
    if (!subscription?.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchReservationAdvisor(subscription, { commitment_type: commitmentType });
      setData(result);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [subscription, commitmentType]);

  useEffect(() => { load(); }, [load]);

  const sync = useCallback(async () => {
    if (!subscription?.trim()) return;
    setSyncing(true);
    try {
      const result = await syncReservationAdvisor(subscription, { trigger_advisor_generate: true });
      setData(result);
      setHideWarnings(false);
    } catch (e) {
      setError(e);
    } finally {
      setSyncing(false);
    }
  }, [subscription]);

  const currency = data?.billing_currency ?? 'CAD';
  const summary = data?.summary ?? {};

  const filteredRecs = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = data?.recommendations ?? [];
    if (q) {
      rows = rows.filter((r) =>
        r.title?.toLowerCase().includes(q)
        || r.resource_id?.toLowerCase().includes(q)
        || r.commitment_type?.toLowerCase().includes(q),
      );
    }
    if (selectedCommitmentId) {
      rows = rows.filter((r) => !r.resource_id || r.resource_id.includes(selectedCommitmentId.split('/').pop()));
    }
    return rows;
  }, [data?.recommendations, search, selectedCommitmentId]);

  const syncButton = <AdvSyncButton onClick={sync} syncing={syncing} loading={loading} />;
  const metaItems = [data?.month && `Spend month: ${data.month}`].filter(Boolean);

  return (
    <AdvancedToolLayout
      title="Reservation advisor"
      pageScope="reservationAdvisor"
      iconKey="reservationAdvisor"
      iconRoute="/reservation-advisor"
      accent="reservations"
      metaItems={metaItems}
      sources={data?.sources}
      warnings={data?.warnings}
      hideWarnings={hideWarnings}
      onDismissWarnings={() => setHideWarnings(true)}
      onRefresh={load}
      loading={loading}
      error={error}
      errorTitle="Could not load reservation advisor"
      headerActions={syncButton}
      hero={{
        isLoading: loading && !data,
        subtitle: data?.month ? `Spend month ${data.month}` : undefined,
        metrics: [
          {
            label: 'Annual opportunity',
            value: fmtCurrency(summary.total_annual_opportunity, currency),
            featured: true,
            tone: (summary.total_annual_opportunity ?? 0) > 0 ? 'success' : 'default',
            sub: `${summary.total_recommendations ?? 0} recommendations`,
          },
          {
            label: 'Coverage estimate',
            value: summary.estimated_coverage_pct != null ? `${summary.estimated_coverage_pct}%` : '—',
            sub: `${summary.active_reservations_count ?? 0} RIs · ${summary.active_savings_plans_count ?? 0} SPs`,
          },
          {
            label: 'VM spend',
            value: fmtCurrency(summary.total_vm_spend_monthly, currency),
            sub: data?.month || 'Current month',
          },
          {
            label: 'Underutilised',
            value: (summary.underutilised_count ?? 0).toLocaleString(),
            tone: (summary.underutilised_count ?? 0) > 0 ? 'warning' : 'default',
            sub: 'below 80% utilisation',
          },
        ],
        footer: (data?.active_commitments ?? []).length > 0 ? (
          <AdvHeroFooter label="Azure inventory" icon={Shield}>
            <span className="adv-hero__plan-chip">
              <strong>{(data?.active_commitments ?? []).length}</strong> active commitments synced from Azure
            </span>
          </AdvHeroFooter>
        ) : null,
      }}
    >
      <AdvFilterChips
        options={[
          { id: 'all', label: 'All' },
          { id: 'reserved_instance', label: 'Reserved instance' },
          { id: 'savings_plan', label: 'Savings plan' },
        ]}
        value={commitmentType}
        onChange={setCommitmentType}
      />

      <FilterBar
        className="waste-filter-bar mb-5"
        search={{ value: search, onChange: setSearch, placeholder: 'Search recommendations…' }}
        onClear={search ? () => setSearch('') : undefined}
        resultCount={{ shown: filteredRecs.length, total: data?.recommendations?.length ?? 0, label: 'recommendations' }}
      />

      <div className="tag-rg-explorer mb-5">
        <div className="tag-rg-explorer__header">
          <div>
            <h3 className="tag-rg-explorer__title">Active commitments and recommendations</h3>
            <p className="tag-rg-explorer__sub">Select a commitment on the left; review purchase recommendations on the right.</p>
          </div>
          {(selectedRecId || selectedCommitmentId) && (
            <button type="button" className="chip active" onClick={() => { setSelectedRecId(''); setSelectedCommitmentId(''); }}>
              Clear selection <X size={12} />
            </button>
          )}
        </div>
        <div className="tag-rg-explorer__grid">
          <div className="tag-rg-explorer__pane tag-rg-explorer__pane--groups">
            <div className="tag-rg-explorer__pane-head">
              <p className="tag-rg-explorer__pane-title">Azure inventory</p>
              <p className="tag-rg-explorer__pane-meta">{(data?.active_commitments ?? []).length} active</p>
            </div>
            <CommitmentTable
              items={data?.active_commitments}
              currency={currency}
              selectedId={selectedCommitmentId}
              onSelect={(id) => setSelectedCommitmentId((v) => (v === id ? '' : id))}
            />
          </div>
          <div className="tag-rg-explorer__pane tag-rg-explorer__pane--resources">
            <div className="tag-rg-explorer__pane-head">
              <p className="tag-rg-explorer__pane-title">Purchase recommendations</p>
              <p className="tag-rg-explorer__pane-meta">{filteredRecs.length.toLocaleString()} showing</p>
            </div>
            {loading ? <AdvSkeleton className="h-48 m-4 rounded-xl" /> : !filteredRecs.length ? (
              <AdvEmptyState
                title="No matches"
                description="Run Sync from Azure to refresh Advisor and inventory."
              />
            ) : (
              <div className="p-3 space-y-2 max-h-[28rem] overflow-auto">
                {filteredRecs.map((rec) => (
                  <RecRow
                    key={rec.id}
                    rec={rec}
                    currency={currency}
                    active={selectedRecId === rec.id}
                    onSelect={(id) => setSelectedRecId((v) => (v === id ? '' : id))}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {!loading && (data?.underutilised_commitments ?? []).length > 0 && (
        <AdvHighlightPanel
          title="Underutilised commitments"
          count={data.underutilised_commitments.length}
          icon={AlertTriangle}
          accent="warning"
        >
          {data.underutilised_commitments.map((item) => (
            <div key={item.id} className="ai-analysis-hp__item">
              <div>
                <p className="tag-rg-table__name">{item.title}</p>
                <p className="tag-rg-table__mono">{item.commitment_type?.replace('_', ' ')}</p>
              </div>
              <div className="text-right">
                {item.utilisation_pct != null && <p className="text-amber-600 font-semibold">{item.utilisation_pct}% utilised</p>}
                {item.wasted_usd > 0 && <p className="text-xs text-red-500">{fmtCurrency(item.wasted_usd, currency)} at risk</p>}
              </div>
            </div>
          ))}
        </AdvHighlightPanel>
      )}
    </AdvancedToolLayout>
  );
}
