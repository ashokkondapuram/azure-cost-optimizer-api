import React, { useMemo, useState } from 'react';
import { Wallet, Plus, Trash2, AlertTriangle, CheckCircle, Edit2 } from 'lucide-react';

/**
 * Budget Manager — Phase 2
 * Create, edit, and monitor Azure cost budgets by subscription,
 * resource group, or tag scope. Ships with seed data so it renders
 * immediately; swap useState for useQuery once the /api/budgets
 * endpoint exists.
 */

const SEED_BUDGETS = [
  { id: 'b1', name: 'Production subscription', scope: 'subscription', amount: 15000, spent: 12340, period: 'monthly', threshold: 85, currency: 'CAD' },
  { id: 'b2', name: 'Dev/test RG', scope: 'resource-group', amount: 3000, spent: 890, period: 'monthly', threshold: 80, currency: 'CAD' },
  { id: 'b3', name: 'AKS cluster costs', scope: 'tag', amount: 8000, spent: 7650, period: 'monthly', threshold: 90, currency: 'CAD' },
  { id: 'b4', name: 'Analytics workloads', scope: 'tag', amount: 5000, spent: 2100, period: 'monthly', threshold: 75, currency: 'CAD' },
];

const EMPTY_FORM = { name: '', scope: 'subscription', amount: '', threshold: 80, period: 'monthly', currency: 'CAD' };

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
  const [budgets, setBudgets] = useState(SEED_BUDGETS);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editId, setEditId] = useState(null);

  const summary = useMemo(() => ({
    total: budgets.reduce((s, b) => s + b.amount, 0),
    spent: budgets.reduce((s, b) => s + b.spent, 0),
    over: budgets.filter((b) => statusFor(b.spent, b.amount, b.threshold) === 'over').length,
    alert: budgets.filter((b) => statusFor(b.spent, b.amount, b.threshold) === 'alert').length,
  }), [budgets]);

  function handleSubmit(e) {
    e.preventDefault();
    const amt = parseFloat(form.amount);
    if (!form.name || isNaN(amt) || amt <= 0) return;
    if (editId) {
      setBudgets((prev) => prev.map((b) => b.id === editId ? { ...b, ...form, amount: amt } : b));
    } else {
      setBudgets((prev) => [...prev, { ...form, id: `b${Date.now()}`, spent: 0, amount: amt }]);
    }
    setForm(EMPTY_FORM);
    setShowForm(false);
    setEditId(null);
  }

  function startEdit(b) {
    setForm({ name: b.name, scope: b.scope, amount: String(b.amount), threshold: b.threshold, period: b.period, currency: b.currency });
    setEditId(b.id);
    setShowForm(true);
  }

  function deleteBudget(id) {
    setBudgets((prev) => prev.filter((b) => b.id !== id));
  }

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <h1 className="page-title icon-inline"><Wallet size={20} /> Budget manager</h1>
          <p className="page-subtitle">Track and enforce Azure cost budgets by subscription, resource group, or tag.</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => { setForm(EMPTY_FORM); setEditId(null); setShowForm(true); }}>
          <Plus size={14} /> New budget
        </button>
      </div>

      {/* Summary KPIs */}
      <div className="grid-4" style={{ marginBottom: '1.25rem' }}>
        <div className="stat-card accent">
          <div className="stat-label">Total budgeted</div>
          <div className="stat-value">${summary.total.toLocaleString()}</div>
          <div className="stat-sub">CAD / month across {budgets.length} budgets</div>
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

      {/* Create / edit form */}
      {showForm && (
        <div className="panel" style={{ marginBottom: '1.25rem' }}>
          <h3 style={{ marginBottom: '0.85rem', fontSize: '0.9rem', fontWeight: 700 }}>
            {editId ? 'Edit budget' : 'New budget'}
          </h3>
          <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.75rem' }}>
            <div>
              <label className="form-label" htmlFor="bm-name">Name</label>
              <input id="bm-name" className="input-field" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Budget name" required />
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
              <label className="form-label" htmlFor="bm-amount">Amount (CAD)</label>
              <input id="bm-amount" className="input-field" type="number" min="1" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} placeholder="e.g. 10000" required />
            </div>
            <div>
              <label className="form-label" htmlFor="bm-threshold">Alert threshold (%)</label>
              <input id="bm-threshold" className="input-field" type="number" min="1" max="100" value={form.threshold} onChange={(e) => setForm((f) => ({ ...f, threshold: Number(e.target.value) }))} />
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem', gridColumn: 'span 2' }}>
              <button type="submit" className="btn btn-primary">{editId ? 'Save changes' : 'Create budget'}</button>
              <button type="button" className="btn btn-ghost" onClick={() => { setShowForm(false); setEditId(null); }}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Budget list */}
      <div className="schedule-list">
        {budgets.map((b) => {
          const p = pct(b.spent, b.amount);
          const status = statusFor(b.spent, b.amount, b.threshold);
          const barColor = status === 'over' ? 'var(--danger)' : status === 'alert' ? 'var(--warning)' : 'var(--success)';
          return (
            <div key={b.id} className="schedule-card">
              <div className="schedule-card__head">
                <StatusIcon status={status} />
                <span className="schedule-card__name">{b.name}</span>
                <span className="toggle-pill" style={{ background: 'var(--surface-offset)', color: 'var(--text2)' }}>{b.scope}</span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.4rem' }}>
                  <button type="button" className="btn btn-ghost" style={{ padding: '0.2rem 0.4rem' }} onClick={() => startEdit(b)} aria-label="Edit"><Edit2 size={13} /></button>
                  <button type="button" className="btn btn-ghost" style={{ padding: '0.2rem 0.4rem', color: 'var(--danger)' }} onClick={() => deleteBudget(b.id)} aria-label="Delete"><Trash2 size={13} /></button>
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
            <p>Create your first budget to start tracking Azure spend against limits.</p>
            <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}><Plus size={14} /> New budget</button>
          </div>
        )}
      </div>
    </div>
  );
}
