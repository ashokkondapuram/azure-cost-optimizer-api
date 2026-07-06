import React, { useMemo, useState } from 'react';
import { PiggyBank, TrendingDown, Calendar, DollarSign } from 'lucide-react';

/**
 * Savings Planner — Phase 2
 * Models pay-as-you-go vs Azure savings plan commitments (1-year / 3-year)
 * and computes break-even and total savings. Swap the static rates for
 * real data from /api/savings-plan/estimate once that endpoint exists.
 */

const PAYG_RATE = 1.0;
const RATES = {
  payg:   { label: 'Pay-as-you-go', multiplier: 1.0,  discount: 0 },
  one:    { label: '1-year savings plan', multiplier: 0.83, discount: 17 },
  three:  { label: '3-year savings plan', multiplier: 0.70, discount: 30 },
};

const SERVICE_PRESETS = [
  { id: 'vms',      label: 'Virtual machines',    monthlyCost: 6200 },
  { id: 'aks',      label: 'AKS clusters',         monthlyCost: 3100 },
  { id: 'sql',      label: 'SQL databases',         monthlyCost: 1800 },
  { id: 'storage',  label: 'Storage accounts',      monthlyCost:  420 },
  { id: 'appsvcs',  label: 'App services',           monthlyCost:  780 },
];

export default function SavingsPlanner() {
  const [monthlyCost, setMonthlyCost] = useState(12300);
  const [plan, setPlan] = useState('one');
  const [selectedServices, setSelectedServices] = useState(new Set(['vms', 'aks']));

  const derivedCost = useMemo(() => {
    const sum = SERVICE_PRESETS
      .filter((s) => selectedServices.has(s.id))
      .reduce((acc, s) => acc + s.monthlyCost, 0);
    return sum || monthlyCost;
  }, [selectedServices, monthlyCost]);

  const rate = RATES[plan];
  const monthlySaving = derivedCost * (1 - rate.multiplier);
  const yearsInPlan = plan === 'three' ? 3 : 1;
  const totalSaving = monthlySaving * 12 * yearsInPlan;
  const breakEvenMonths = rate.discount === 0 ? null : Math.ceil((derivedCost * rate.multiplier * 2) / (monthlySaving || 1));

  function toggleService(id) {
    setSelectedServices((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <h1 className="page-title icon-inline"><PiggyBank size={20} /> Savings planner</h1>
          <p className="page-subtitle">Model Azure savings plan commitments vs pay-as-you-go and estimate total savings.</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 360px) 1fr', gap: '1.25rem', alignItems: 'start' }}>
        {/* Controls */}
        <div className="panel">
          <h3 style={{ fontSize: '0.88rem', fontWeight: 700, marginBottom: '0.85rem' }}>Configuration</h3>

          <div style={{ marginBottom: '1rem' }}>
            <label className="form-label" htmlFor="sp-cost">Monthly baseline cost (CAD)</label>
            <input
              id="sp-cost"
              className="input-field"
              type="number"
              min="1"
              value={monthlyCost}
              onChange={(e) => { setMonthlyCost(Number(e.target.value)); setSelectedServices(new Set()); }}
            />
            <p style={{ fontSize: '0.75rem', color: 'var(--text3)', marginTop: '0.3rem' }}>Or pick services below to auto-fill.</p>
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <div className="form-label" style={{ marginBottom: '0.4rem' }}>Commitment term</div>
            {Object.entries(RATES).map(([key, r]) => (
              <label key={key} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem', cursor: 'pointer', fontSize: '0.85rem' }}>
                <input type="radio" name="sp-plan" value={key} checked={plan === key} onChange={() => setPlan(key)} />
                {r.label}{r.discount > 0 ? ` (${r.discount}% off)` : ''}
              </label>
            ))}
          </div>

          <div>
            <div className="form-label" style={{ marginBottom: '0.4rem' }}>Services to model</div>
            {SERVICE_PRESETS.map((s) => (
              <label key={s.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem', cursor: 'pointer', fontSize: '0.82rem' }}>
                <input
                  type="checkbox"
                  checked={selectedServices.has(s.id)}
                  onChange={() => toggleService(s.id)}
                />
                {s.label} <span style={{ color: 'var(--text3)', marginLeft: 'auto' }}>${s.monthlyCost.toLocaleString()}/mo</span>
              </label>
            ))}
          </div>
        </div>

        {/* Results */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="grid-4">
            <div className="stat-card accent">
              <div className="stat-label">Monthly cost (PAYG)</div>
              <div className="stat-value">${derivedCost.toLocaleString()}</div>
              <div className="stat-sub">CAD, no commitment</div>
            </div>
            <div className="stat-card success">
              <div className="stat-label">Monthly saving</div>
              <div className="stat-value">${Math.round(monthlySaving).toLocaleString()}</div>
              <div className="stat-sub">{rate.discount}% discount applied</div>
            </div>
            <div className="stat-card info">
              <div className="stat-label">Total saving ({yearsInPlan}yr)</div>
              <div className="stat-value">${Math.round(totalSaving).toLocaleString()}</div>
              <div className="stat-sub">Over {yearsInPlan * 12} months</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Break-even</div>
              <div className="stat-value">{breakEvenMonths ? `${breakEvenMonths} mo` : '—'}</div>
              <div className="stat-sub">{breakEvenMonths ? 'Months to recoup' : 'No commitment'}</div>
            </div>
          </div>

          {/* Comparison table */}
          <div className="panel">
            <h3 style={{ fontSize: '0.88rem', fontWeight: 700, marginBottom: '0.85rem' }}>Plan comparison</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th style={{ textAlign: 'left', padding: '0.5rem 0.6rem', color: 'var(--text2)', fontWeight: 600 }}>Plan</th>
                  <th style={{ textAlign: 'right', padding: '0.5rem 0.6rem', color: 'var(--text2)', fontWeight: 600 }}>Monthly</th>
                  <th style={{ textAlign: 'right', padding: '0.5rem 0.6rem', color: 'var(--text2)', fontWeight: 600 }}>Annual</th>
                  <th style={{ textAlign: 'right', padding: '0.5rem 0.6rem', color: 'var(--text2)', fontWeight: 600 }}>Total saving</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(RATES).map(([key, r]) => {
                  const monthly = Math.round(derivedCost * r.multiplier);
                  const annual = monthly * 12;
                  const saving = Math.round((derivedCost - derivedCost * r.multiplier) * 12 * (key === 'three' ? 3 : 1));
                  const isSelected = key === plan;
                  return (
                    <tr key={key} style={{ borderBottom: '1px solid var(--border)', background: isSelected ? 'var(--primary-muted)' : 'transparent', cursor: 'pointer' }} onClick={() => setPlan(key)}>
                      <td style={{ padding: '0.55rem 0.6rem', fontWeight: isSelected ? 700 : 400 }}>{r.label}</td>
                      <td style={{ padding: '0.55rem 0.6rem', textAlign: 'right' }}>${monthly.toLocaleString()}</td>
                      <td style={{ padding: '0.55rem 0.6rem', textAlign: 'right' }}>${annual.toLocaleString()}</td>
                      <td style={{ padding: '0.55rem 0.6rem', textAlign: 'right', color: saving > 0 ? 'var(--success)' : 'var(--text2)' }}>
                        {saving > 0 ? `$${saving.toLocaleString()}` : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
