import React, { useState, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, BellRing, Plus, Trash2, AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired } from '../components/QueryStates';

const PERIODS = [
  { label: '30 days', value: 30 },
  { label: '60 days', value: 60 },
  { label: '90 days', value: 90 },
];

function ForecastChart({ points = [], forecastPoints = [], currency = 'CAD' }) {
  if (!points.length && !forecastPoints.length) return (
    <div className="forecast-empty">
      <TrendingUp size={32} className="text-muted" />
      <p>No cost data available to generate forecast.</p>
    </div>
  );

  const all = [...points, ...forecastPoints];
  const maxVal = Math.max(...all.map(p => p.value || 0), 1);
  const fmt = (v) => `${currency} ${(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

  return (
    <div className="forecast-chart">
      <div className="forecast-chart__bars">
        {points.map((p, i) => (
          <div key={i} className="forecast-bar forecast-bar--actual" style={{ '--h': `${((p.value || 0) / maxVal) * 100}%` }}>
            <span className="forecast-bar__tip">{fmt(p.value)}</span>
          </div>
        ))}
        {forecastPoints.map((p, i) => (
          <div key={`f${i}`} className="forecast-bar forecast-bar--projected" style={{ '--h': `${((p.value || 0) / maxVal) * 100}%` }}>
            <span className="forecast-bar__tip">{fmt(p.value)}</span>
          </div>
        ))}
      </div>
      <div className="forecast-chart__legend">
        <span className="forecast-legend forecast-legend--actual">Actual</span>
        <span className="forecast-legend forecast-legend--projected">Projected</span>
      </div>
    </div>
  );
}

function BudgetAlert({ budget, onDelete }) {
  const pct = budget.limit > 0 ? Math.round((budget.current / budget.limit) * 100) : 0;
  const status = pct >= 100 ? 'exceeded' : pct >= 80 ? 'warning' : 'ok';
  return (
    <div className={`budget-alert-row budget-alert-row--${status}`}>
      <div className="budget-alert-row__info">
        <span className="budget-alert-row__name">{budget.name}</span>
        <span className="budget-alert-row__scope">{budget.scope}</span>
      </div>
      <div className="budget-alert-row__bar-wrap">
        <div className="budget-alert-row__bar">
          <div className="budget-alert-row__fill" style={{ width: `${Math.min(pct, 100)}%` }} />
        </div>
        <span className="budget-alert-row__pct">{pct}%</span>
      </div>
      <div className="budget-alert-row__amounts">
        <span className="budget-alert-row__current">{(budget.current || 0).toLocaleString()}</span>
        <span className="budget-alert-row__sep">/</span>
        <span className="budget-alert-row__limit">{(budget.limit || 0).toLocaleString()}</span>
      </div>
      <div className="budget-alert-row__status">
        {status === 'exceeded' && <AlertTriangle size={14} className="text-danger" />}
        {status === 'warning'  && <AlertTriangle size={14} className="text-warning" />}
        {status === 'ok'       && <CheckCircle   size={14} className="text-success" />}
      </div>
      <button type="button" className="btn btn-sm btn-ghost budget-alert-row__del" onClick={() => onDelete(budget.id)} title="Remove">
        <Trash2 size={12} />
      </button>
    </div>
  );
}

export default function CostForecast() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const [period, setPeriod] = useState(30);
  const [budgets, setBudgets] = useState([
    { id: 1, name: 'Monthly Compute', scope: 'Subscription', limit: 5000, current: 4200 },
    { id: 2, name: 'AKS Budget',      scope: 'Resource Group', limit: 2000, current: 2150 },
  ]);
  const [showAddBudget, setShowAddBudget] = useState(false);
  const [newBudget, setNewBudget] = useState({ name: '', scope: 'Subscription', limit: '' });

  const addBudget = () => {
    if (!newBudget.name || !newBudget.limit) return;
    setBudgets(prev => [...prev, {
      id: Date.now(),
      name: newBudget.name,
      scope: newBudget.scope,
      limit: Number(newBudget.limit),
      current: 0,
    }]);
    setNewBudget({ name: '', scope: 'Subscription', limit: '' });
    setShowAddBudget(false);
  };

  const deleteBudget = (id) => setBudgets(prev => prev.filter(b => b.id !== id));

  // Mock forecast data – replace with real API calls
  const mockActual = Array.from({ length: 10 }, (_, i) => ({ label: `W${i+1}`, value: 1200 + Math.random() * 400 }));
  const mockForecast = Array.from({ length: period / 7 }, (_, i) => ({ label: `F${i+1}`, value: 1400 + i * 80 + Math.random() * 200 }));

  const projectedTotal = mockForecast.reduce((s, p) => s + p.value, 0);
  const actualMtd = mockActual.reduce((s, p) => s + p.value, 0);

  return (
    <div className="page-shell cost-forecast-page">
      <PageHeader
        title="Cost Forecast & Budget Alerts"
        subtitle={`Projected spend and budget thresholds for the active subscription`}
      >
        <div className="segmented">
          {PERIODS.map(p => (
            <button key={p.value} type="button" className={`segmented__btn${period === p.value ? ' active' : ''}`}
              onClick={() => setPeriod(p.value)}>{p.label}</button>
          ))}
        </div>
      </PageHeader>

      {!subscription && <SubscriptionRequired message="Select a subscription to view forecasts." />}

      {subscription && (
        <>
          {/* KPI row */}
          <div className="grid-3" style={{ marginBottom: '1.25rem' }}>
            <div className="stat-card accent">
              <div className="stat-label">Actual MTD</div>
              <div className="stat-value">{currency} {actualMtd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
              <div className="stat-sub">Current billing period</div>
            </div>
            <div className="stat-card warning">
              <div className="stat-label">Projected ({period}d)</div>
              <div className="stat-value">{currency} {projectedTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
              <div className="stat-sub">Based on recent trend</div>
            </div>
            <div className="stat-card danger">
              <div className="stat-label">Budgets at Risk</div>
              <div className="stat-value">{budgets.filter(b => (b.current / b.limit) >= 0.8).length}</div>
              <div className="stat-sub">≥80% of limit consumed</div>
            </div>
          </div>

          {/* Chart */}
          <div className="card" style={{ marginBottom: '1.25rem' }}>
            <div className="card-section-head">
              <TrendingUp size={16} className="text-primary" />
              <h3>Spend Trend &amp; Forecast</h3>
              <span className="badge badge-info" style={{ marginLeft: 'auto' }}>Beta</span>
            </div>
            <ForecastChart points={mockActual} forecastPoints={mockForecast} currency={currency} />
          </div>

          {/* Budget Alerts */}
          <div className="card">
            <div className="card-section-head" style={{ marginBottom: '0.85rem' }}>
              <BellRing size={16} className="text-warning" />
              <h3>Budget Alerts</h3>
              <button type="button" className="btn btn-sm btn-primary" style={{ marginLeft: 'auto' }}
                onClick={() => setShowAddBudget(s => !s)}>
                <Plus size={13} /> Add Budget
              </button>
            </div>

            {showAddBudget && (
              <div className="budget-add-form">
                <input className="" placeholder="Budget name" value={newBudget.name}
                  onChange={e => setNewBudget(p => ({ ...p, name: e.target.value }))} />
                <select value={newBudget.scope}
                  onChange={e => setNewBudget(p => ({ ...p, scope: e.target.value }))}>
                  <option>Subscription</option>
                  <option>Resource Group</option>
                  <option>Tag</option>
                </select>
                <input type="number" placeholder="Limit (CAD)" value={newBudget.limit}
                  onChange={e => setNewBudget(p => ({ ...p, limit: e.target.value }))} />
                <button type="button" className="btn btn-sm btn-primary" onClick={addBudget}>Save</button>
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => setShowAddBudget(false)}>Cancel</button>
              </div>
            )}

            <div className="budget-alert-list">
              {budgets.length === 0 && (
                <div className="empty-state"><Info size={22} /><p>No budgets configured yet.</p></div>
              )}
              {budgets.map(b => <BudgetAlert key={b.id} budget={b} onDelete={deleteBudget} />)}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
