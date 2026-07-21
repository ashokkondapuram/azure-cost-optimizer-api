import React, { useContext, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Wallet, Plus, Trash2, AlertTriangle, CheckCircle, Edit2 } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import { AppCtx } from '../App';
import { LoadingState, QueryErrorState } from '../components/QueryStates';
import {
  createBudget,
  deleteBudget,
  fetchSubscriptionBudgets,
  mapBudgetForManager,
  updateBudget,
} from '../api/budgets';

const EMPTY_FORM = {
  name: '',
  scope: 'subscription',
  amount: '',
  threshold: 80,
  period: 'monthly',
  currency: 'CAD',
};

function pct(spent, amount) {
  if (!amount) return 0;
  return Math.min(100, ((spent / amount) * 100)).toFixed(1);
}

function statusFor(spent, amount, threshold) {
  const p = (spent / (amount || 1)) * 100;
  if (p >= 100) return 'over';
  if (p >= threshold) return 'alert';
  return 'ok';
}

function StatusIcon({ status }) {
  if (status === 'over') return <AlertTriangle size={15} style={{ color: 'var(--danger)' }} />;
  if (status === 'alert') return <AlertTriangle size={15} style={{ color: 'var(--warning)' }} />;
  return <CheckCircle size={15} style={{ color: 'var(--success)' }} />;
}

export default function BudgetManager() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM, currency });
  const [editName, setEditName] = useState(null);

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['budgets', subscription],
    queryFn: () => fetchSubscriptionBudgets(subscription),
    enabled: !!subscription,
    staleTime: 2 * 60_000,
  });

  const budgets = useMemo(
    () => (data?.budgets || []).map(mapBudgetForManager),
    [data],
  );

  const summary = useMemo(() => ({
    total: budgets.reduce((s, b) => s + b.amount, 0),
    spent: budgets.reduce((s, b) => s + b.spent, 0),
    over: budgets.filter((b) => statusFor(b.spent, b.amount, b.threshold) === 'over').length,
    alert: budgets.filter((b) => statusFor(b.spent, b.amount, b.threshold) === 'alert').length,
  }), [budgets]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const amt = parseFloat(form.amount);
      if (!subscription || !form.name || Number.isNaN(amt) || amt <= 0) {
        throw new Error('Enter a valid budget name and amount.');
      }
      const payload = {
        subscription_id: subscription,
        name: form.name,
        monthly_limit: amt,
        currency: form.currency || currency,
        scope: form.scope,
        period: form.period,
        alert_thresholds: [Number(form.threshold) || 80],
      };
      if (editName) {
        return updateBudget(subscription, editName, {
          monthly_limit: amt,
          alert_thresholds: [Number(form.threshold) || 80],
          scope: form.scope,
          period: form.period,
        });
      }
      return createBudget(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgets', subscription] });
      setForm({ ...EMPTY_FORM, currency });
      setShowForm(false);
      setEditName(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: ({ name }) => deleteBudget(subscription, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['budgets', subscription] }),
  });

  function startEdit(b) {
    if (b.source === 'azure') return;
    setForm({
      name: b.name,
      scope: b.scope,
      amount: String(b.amount),
      threshold: b.threshold,
      period: b.period,
      currency: b.currency,
    });
    setEditName(b.name);
    setShowForm(true);
  }

  if (!subscription) {
    return (
      <div className="page-shell">
        <PageHeader title="Budget manager" subtitle="Select a subscription to view budgets." iconKey="budgetsNav" iconRoute="/budgets" />
        <div className="wiz-empty"><strong>Select a subscription</strong> to load Azure and custom budgets.</div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        title="Budget manager"
        pageScope="budgets"
        iconKey="budgetsNav"
        iconRoute="/budgets"
      >
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => { setForm({ ...EMPTY_FORM, currency }); setEditName(null); setShowForm(true); }}
        >
          <Plus size={14} /> New budget
        </button>
      </PageHeader>

      {isLoading && <LoadingState message="Loading budgets…" />}
      {isError && <QueryErrorState error={error} onRetry={refetch} />}

      {!isLoading && !isError && (
        <>
          <div className="grid-4" style={{ marginBottom: '1.25rem' }}>
            <div className="stat-card accent">
              <div className="stat-label">Total budgeted</div>
              <div className="stat-value">${summary.total.toLocaleString()}</div>
              <div className="stat-sub">{currency} / month across {budgets.length} budgets</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Total spent MTD</div>
              <div className="stat-value">${summary.spent.toLocaleString()}</div>
              <div className="stat-sub">{pct(summary.spent, summary.total)}% of total budget</div>
            </div>
            <div className="stat-card danger">
              <div className="stat-label">Over budget</div>
              <div className="stat-value">{summary.over}</div>
              <div className="stat-sub">Budget{summary.over !== 1 ? 's' : ''} exceeded</div>
            </div>
            <div className="stat-card warning">
              <div className="stat-label">Threshold alerts</div>
              <div className="stat-value">{summary.alert}</div>
              <div className="stat-sub">Approaching limit</div>
            </div>
          </div>

          {showForm && (
            <div className="panel" style={{ marginBottom: '1.25rem' }}>
              <h3 style={{ marginBottom: '0.85rem', fontSize: '0.9rem', fontWeight: 700 }}>
                {editName ? 'Edit budget' : 'New budget'}
              </h3>
              <form
                onSubmit={(e) => { e.preventDefault(); saveMutation.mutate(); }}
                style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.75rem' }}
              >
                <div>
                  <label className="form-label" htmlFor="bm-name">Name</label>
                  <input id="bm-name" className="input-field" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Budget name" required disabled={!!editName} />
                </div>
                <div>
                  <label className="form-label" htmlFor="bm-scope">Scope</label>
                  <select id="bm-scope" className="select-field" value={form.scope} onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value }))}>
                    <option value="subscription">Subscription</option>
                    <option value="resource-group">Resource group</option>
                    <option value="tag">Tag</option>
                  </select>
                </div>
                <div>
                  <label className="form-label" htmlFor="bm-amount">Amount ({currency})</label>
                  <input id="bm-amount" className="input-field" type="number" min="1" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} placeholder="e.g. 10000" required />
                </div>
                <div>
                  <label className="form-label" htmlFor="bm-threshold">Alert threshold (%)</label>
                  <input id="bm-threshold" className="input-field" type="number" min="1" max="100" value={form.threshold} onChange={(e) => setForm((f) => ({ ...f, threshold: Number(e.target.value) }))} />
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem', gridColumn: 'span 2' }}>
                  <button type="submit" className="btn btn-primary" disabled={saveMutation.isPending}>
                    {saveMutation.isPending ? 'Saving…' : editName ? 'Save changes' : 'Create budget'}
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={() => { setShowForm(false); setEditName(null); }}>Cancel</button>
                </div>
              </form>
            </div>
          )}

          <div className="schedule-list">
            {budgets.map((b) => {
              const p = pct(b.spent, b.amount);
              const status = statusFor(b.spent, b.amount, b.threshold);
              const barColor = status === 'over' ? 'var(--danger)' : status === 'alert' ? 'var(--warning)' : 'var(--success)';
              const isAzure = b.source === 'azure';
              return (
                <div key={b.id} className="schedule-card">
                  <div className="schedule-card__head">
                    <StatusIcon status={status} />
                    <span className="schedule-card__name">{b.name}</span>
                    <span className="toggle-pill" style={{ background: 'var(--surface-offset)', color: 'var(--text2)' }}>{b.scope}</span>
                    {isAzure && (
                      <span className="toggle-pill" style={{ background: 'var(--primary-muted)', color: 'var(--primary)' }}>Azure</span>
                    )}
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.4rem' }}>
                      {!isAzure && (
                        <>
                          <button type="button" className="btn btn-ghost" style={{ padding: '0.2rem 0.4rem' }} onClick={() => startEdit(b)} aria-label="Edit"><Edit2 size={13} /></button>
                          <button type="button" className="btn btn-ghost" style={{ padding: '0.2rem 0.4rem', color: 'var(--danger)' }} onClick={() => deleteMutation.mutate({ name: b.name })} aria-label="Delete"><Trash2 size={13} /></button>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="schedule-card__body">
                    <div className="schedule-card__row"><strong>Spent:</strong> ${b.spent.toLocaleString()} / ${b.amount.toLocaleString()} {b.currency}</div>
                    <div className="schedule-card__row"><strong>Period:</strong> {b.period} &nbsp;·&nbsp; <strong>Alert at:</strong> {b.threshold}%</div>
                  </div>
                  <div style={{ padding: '0 1rem 0.85rem' }}>
                    <div className="score-bar-wrap" style={{ width: '100%' }}>
                      <div className="score-bar" style={{ flex: 1 }}>
                        <div className="score-bar__fill" style={{ width: `${p}%`, background: barColor }} />
                      </div>
                      <span className="score-bar__label">{p}%</span>
                    </div>
                  </div>
                </div>
              );
            })}
            {budgets.length === 0 && (
              <div className="empty-state">
                <Wallet size={40} />
                <h3>No budgets yet</h3>
                <p>Sync costs to pull Azure budgets, or create a custom budget threshold.</p>
                <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}><Plus size={14} /> New budget</button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
