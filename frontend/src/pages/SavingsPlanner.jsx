/**
 * Savings Planner — live Azure cost + commitment modelling.
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { TrendingDown, Sparkles, Cloud } from 'lucide-react';
import { fetchSavingsEstimate, syncSavingsPlanner } from '../api/savingsPlanner';
import AdvancedToolLayout, { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';
import {
  AdvSkeleton,
  AdvSyncButton,
  AdvPageCard,
  AdvPageStack,
  AdvEmptyState,
  AdvSeverityBadge,
  fmtCurrency,
} from '../components/advanced/AdvUI';
import { AdvHeroFooter } from '../components/advanced/AdvancedToolHero';

const SOURCE_LABELS = {
  azure_live: 'Azure live cost',
  database: 'Synced DB',
  empty: 'No data',
};

export default function SavingsPlanner() {
  const { subscription } = useAdvancedSubscription();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState(null);
  const [planId, setPlanId] = useState('savings_plan_1yr');
  const [excludedCategories, setExcludedCategories] = useState(new Set());
  const [lookbackDays, setLookbackDays] = useState(30);
  const [hideWarnings, setHideWarnings] = useState(false);

  const includedCategories = useMemo(() => {
    const all = (data?.all_categories ?? []).map((c) => c.id);
    if (!all.length || excludedCategories.size === 0) return undefined;
    return all.filter((id) => !excludedCategories.has(id));
  }, [data?.all_categories, excludedCategories]);

  const load = useCallback(async () => {
    if (!subscription?.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchSavingsEstimate(subscription, {
        lookback_days: lookbackDays,
        categories: includedCategories,
        include_live_azure: true,
      });
      setData(result);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [subscription, lookbackDays, includedCategories]);

  const sync = useCallback(async () => {
    if (!subscription?.trim()) return;
    setSyncing(true);
    setError(null);
    try {
      const result = await syncSavingsPlanner(subscription, {
        lookback_days: lookbackDays,
        categories: includedCategories,
        trigger_advisor_generate: true,
      });
      setData(result);
      setHideWarnings(false);
    } catch (e) {
      setError(e);
    } finally {
      setSyncing(false);
    }
  }, [subscription, lookbackDays, includedCategories]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    setExcludedCategories(new Set());
    setPlanId('savings_plan_1yr');
    setHideWarnings(false);
  }, [subscription]);

  useEffect(() => {
    if (data?.recommended_plan_id) setPlanId(data.recommended_plan_id);
  }, [data?.recommended_plan_id]);

  const currency = data?.billing_currency ?? 'CAD';
  const baseline = data?.monthly_baseline ?? 0;
  const plans = data?.plans ?? [];
  const activePlan = plans.find((p) => p.id === planId) ?? plans[0];
  const categories = data?.all_categories ?? [];
  const activeCommitments = data?.active_commitments ?? [];
  const advisorRecs = data?.advisor_recommendations ?? [];
  const capacityRecs = data?.azure_reservation_recommendations ?? [];

  const toggleCategory = (id) => {
    setExcludedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const years = activePlan?.years || 1;
  const breakEvenMonths = activePlan?.monthly_saving > 0
    ? Math.max(1, Math.ceil((baseline * (activePlan?.multiplier ?? 1) * 2) / activePlan.monthly_saving))
    : null;

  const costSourceLabel = SOURCE_LABELS[data?.sources?.cost_baseline] ?? data?.source;
  const metaItems = [
    `${lookbackDays}-day window`,
    costSourceLabel && `Baseline: ${costSourceLabel}`,
    data?.period_start && data?.period_end && `${data.period_start} – ${data.period_end}`,
  ].filter(Boolean);

  const recommendedPlan = plans.find((p) => p.id === data?.recommended_plan_id);

  return (
    <AdvancedToolLayout
      title="Savings planner"
      subtitle="Model savings plans and reserved instances using live Azure cost data, Advisor, and your active commitments."
      iconKey="savingsPlanner"
      iconRoute="/savings-planner"
      accent="savings"
      metaItems={metaItems}
      sources={data?.sources}
      warnings={data?.warnings}
      hideWarnings={hideWarnings}
      onDismissWarnings={() => setHideWarnings(true)}
      onRefresh={load}
      loading={loading}
      error={error}
      errorTitle="Could not load savings estimate"
      headerActions={<AdvSyncButton onClick={sync} syncing={syncing} loading={loading} />}
      hero={{
        isLoading: loading && !data,
        metrics: [
          {
            label: 'Monthly baseline',
            value: fmtCurrency(baseline, currency),
            featured: true,
            sub: costSourceLabel || 'Pay-as-you-go',
          },
          {
            label: 'Advisor opportunity',
            value: fmtCurrency(data?.advisor_opportunity_monthly, currency),
            tone: (data?.advisor_opportunity_monthly ?? 0) > 0 ? 'success' : 'default',
            sub: `${advisorRecs.length} recs`,
          },
          {
            label: 'RI recommendations',
            value: fmtCurrency(data?.azure_capacity_opportunity_monthly, currency),
            tone: (data?.azure_capacity_opportunity_monthly ?? 0) > 0 ? 'success' : 'default',
            sub: `${capacityRecs.length} from Azure`,
          },
          {
            label: 'Active commitments',
            value: activeCommitments.length.toLocaleString(),
            sub: `${lookbackDays}d window`,
          },
        ],
        footer: recommendedPlan && recommendedPlan.id !== 'payg' ? (
          <AdvHeroFooter label="Recommended plan" icon={Sparkles}>
            <span className="adv-hero__plan-chip">
              <strong>{recommendedPlan.label}</strong>
              · {fmtCurrency(recommendedPlan.monthly_saving, currency)}/mo saving
              {recommendedPlan.data_source === 'azure' && ' · Azure-backed'}
            </span>
          </AdvHeroFooter>
        ) : null,
      }}
    >
      <div className="savings-planner-grid">
        <AdvPageCard
          title="Configuration"
          subtitle="Pick services to include in the baseline, then compare commitment options."
          className="savings-planner-controls"
        >
          <div className="savings-planner-controls__body">
            <div className="anomaly-slider">
              <div className="anomaly-slider__label">
                <span>Spend window</span>
                <span className="anomaly-slider__value">{lookbackDays}d</span>
              </div>
              <input
                type="range"
                min={7}
                max={90}
                step={1}
                value={lookbackDays}
                disabled={loading}
                onChange={(e) => setLookbackDays(Number(e.target.value))}
              />
              <p className="anomaly-slider__help">Days of Azure cost data summed into the baseline (live query when available).</p>
            </div>

            <div>
              <p className="tag-rg-explorer__pane-title" style={{ marginBottom: '0.5rem' }}>Services to model</p>
              {loading && !categories.length ? (
                <AdvSkeleton className="h-24 rounded-lg" />
              ) : !categories.length ? (
                <AdvEmptyState
                  title="No spend data"
                  description="Sync from Azure or run a cost sync to populate service costs."
                  icon={Cloud}
                />
              ) : (
                <div className="savings-planner-categories">
                  {categories.map((cat) => {
                    const included = !excludedCategories.has(cat.id);
                    return (
                      <label key={cat.id} className={`savings-planner-category${included ? ' savings-planner-category--on' : ''}`}>
                        <input type="checkbox" checked={included} onChange={() => toggleCategory(cat.id)} />
                        <span className="savings-planner-category__label">{cat.label}</span>
                        <span className="savings-planner-category__cost">{fmtCurrency(cat.monthly_cost, currency)}/mo</span>
                      </label>
                    );
                  })}
                </div>
              )}
              {excludedCategories.size > 0 && (
                <button type="button" className="chip mt-2" onClick={() => setExcludedCategories(new Set())}>
                  Include all services
                </button>
              )}
            </div>
          </div>
        </AdvPageCard>

        <AdvPageStack className="savings-planner-results">
          {loading && !data ? (
            <AdvSkeleton className="h-48 rounded-xl" />
          ) : data?.message && !categories.length ? (
            <AdvEmptyState
              title={data.message}
              description="Use Sync from Azure to pull live cost and commitment data."
              icon={Cloud}
            />
          ) : (
            <>
              <AdvPageCard
                title="Plan comparison"
                subtitle="Click a row to select a commitment scenario. Azure-backed savings override static estimates."
                className="savings-planner-compare"
                actions={data?.recommended_plan_id && (
                  <span className="chip active">
                    <Sparkles size={12} /> Recommended: {plans.find((p) => p.id === data.recommended_plan_id)?.label}
                  </span>
                )}
                noPadding
              >
                <div className="tag-rg-explorer__scroll">
                  <table className="tag-rg-table">
                    <thead>
                      <tr>
                        {['Plan', 'Monthly', 'Annual', 'Total saving', 'Discount', 'Source'].map((h) => (
                          <th key={h}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {plans.map((p) => (
                        <tr
                          key={p.id}
                          className={`tag-rg-table__row tag-rg-table__row--clickable${planId === p.id ? ' tag-rg-table__row--active' : ''}`}
                          onClick={() => setPlanId(p.id)}
                          role="button"
                          tabIndex={0}
                        >
                          <td className="tag-rg-table__name">{p.label}</td>
                          <td className="tag-rg-table__count">{fmtCurrency(p.monthly_cost, currency)}</td>
                          <td className="tag-rg-table__count">{fmtCurrency(p.annual_cost, currency)}</td>
                          <td className="tag-rg-table__count" style={{ color: p.total_saving > 0 ? 'var(--success-text)' : undefined }}>
                            {p.total_saving > 0 ? fmtCurrency(p.total_saving, currency) : '—'}
                          </td>
                          <td>
                            {p.discount_pct > 0 ? (
                              <span className="anomaly-pct anomaly-pct--drop">{p.discount_pct}%</span>
                            ) : '—'}
                          </td>
                          <td>
                            <span className={`chip${p.data_source === 'azure' ? ' active' : ''}`}>
                              {p.data_source === 'azure' ? 'Azure' : 'Estimate'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </AdvPageCard>

              {activeCommitments.length > 0 && (
                <AdvPageCard title="Active commitments from Azure" subtitle="Reservations and savings plans currently applied to this subscription" noPadding>
                  <div className="tag-rg-explorer__scroll" style={{ maxHeight: '14rem' }}>
                    <table className="tag-rg-table">
                      <thead><tr>{['Name', 'Type', 'Term', 'Utilization'].map((h) => <th key={h}>{h}</th>)}</tr></thead>
                      <tbody>
                        {activeCommitments.map((c) => (
                          <tr key={c.id} className="tag-rg-table__row">
                            <td className="tag-rg-table__name" title={c.id}>{c.display_name || c.name}</td>
                            <td>{c.commitment_type === 'savings_plan' ? 'Savings plan' : 'Reservation'}</td>
                            <td>{c.term || '—'}</td>
                            <td className="tag-rg-table__count">{c.utilization_percent != null ? `${c.utilization_percent}%` : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </AdvPageCard>
              )}

              {advisorRecs.length > 0 && (
                <AdvPageCard title="Azure Advisor recommendations" subtitle="Commitment opportunities from Azure Advisor cost recommendations" noPadding>
                  <div className="tag-rg-explorer__scroll" style={{ maxHeight: '14rem' }}>
                    <table className="tag-rg-table">
                      <thead><tr>{['Recommendation', 'Type', 'Est. savings/mo'].map((h) => <th key={h}>{h}</th>)}</tr></thead>
                      <tbody>
                        {advisorRecs.map((r) => (
                          <tr key={r.id} className="tag-rg-table__row">
                            <td className="tag-rg-table__name" title={r.detail}>{r.title}</td>
                            <td>{r.commitment_type === 'savings_plan' ? 'Savings plan' : 'Reservation'}</td>
                            <td className="tag-rg-table__count">{fmtCurrency(r.estimated_monthly_savings, currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </AdvPageCard>
              )}

              {capacityRecs.length > 0 && (
                <AdvPageCard title="Azure reservation purchase recommendations" subtitle="Live recommendations from Azure Capacity API" noPadding>
                  <div className="tag-rg-explorer__scroll" style={{ maxHeight: '14rem' }}>
                    <table className="tag-rg-table">
                      <thead><tr>{['SKU', 'Term', 'Qty', 'Est. savings/mo'].map((h) => <th key={h}>{h}</th>)}</tr></thead>
                      <tbody>
                        {capacityRecs.map((r) => (
                          <tr key={r.id} className="tag-rg-table__row">
                            <td className="tag-rg-table__name">{r.sku_name || r.title}</td>
                            <td>{r.term || `${r.years}yr`}</td>
                            <td className="tag-rg-table__count">{r.recommended_quantity ?? '—'}</td>
                            <td className="tag-rg-table__count">{fmtCurrency(r.monthly_saving, currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </AdvPageCard>
              )}

              {(data?.commitment_opportunities ?? []).length > 0 && (
                <AdvPageCard title="Engine commitment findings" subtitle="Open findings that suggest reservations or savings plans" noPadding>
                  <div className="tag-rg-explorer__scroll" style={{ maxHeight: '14rem' }}>
                    <table className="tag-rg-table">
                      <thead><tr>{['Finding', 'Severity', 'Est. savings/mo'].map((h) => <th key={h}>{h}</th>)}</tr></thead>
                      <tbody>
                        {data.commitment_opportunities.map((o) => (
                          <tr key={o.finding_id} className="tag-rg-table__row">
                            <td className="tag-rg-table__name" title={o.title}>{o.title}</td>
                            <td><AdvSeverityBadge severity={o.severity} /></td>
                            <td className="tag-rg-table__count">{fmtCurrency(o.estimated_savings_monthly, currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </AdvPageCard>
              )}

              {breakEvenMonths && planId !== 'payg' && (
                <div className="ai-analysis-hero-banner ai-analysis-hero-banner--ok">
                  <TrendingDown size={16} className="inline mr-2" />
                  Estimated break-even for <strong>{activePlan?.label}</strong>: {breakEvenMonths} months at current baseline.
                </div>
              )}
            </>
          )}
        </AdvPageStack>
      </div>
    </AdvancedToolLayout>
  );
}
