import React, { useMemo, useState } from 'react';
import { ShieldCheck, ShieldAlert, ShieldX, Filter } from 'lucide-react';

/**
 * Policy Enforcement — Phase 2
 * Surfaces Azure Policy-style compliance results focused on cost
 * guardrails: required tags, allowed SKUs/regions, and public IP
 * restrictions.
 */

const SEED_POLICIES = [
  { id: 'p1', name: 'Require cost-center tag',   category: 'Tagging',    scope: 'All subscriptions',        compliant: 214, noncompliant: 37, severity: 'high' },
  { id: 'p2', name: 'Deny public IP on storage', category: 'Network',    scope: 'Production subscriptions', compliant:  58, noncompliant:  2, severity: 'critical' },
  { id: 'p3', name: 'Allowed VM SKUs only',       category: 'Compute',    scope: 'All subscriptions',        compliant: 132, noncompliant:  9, severity: 'medium' },
  { id: 'p4', name: 'Allowed regions',            category: 'Governance', scope: 'All subscriptions',        compliant: 401, noncompliant:  0, severity: 'low' },
  { id: 'p5', name: 'Require environment tag',    category: 'Tagging',    scope: 'All subscriptions',        compliant: 198, noncompliant: 53, severity: 'high' },
  { id: 'p6', name: 'Deny oversized dev VMs',     category: 'Compute',    scope: 'Dev/test subscriptions',   compliant:  44, noncompliant: 11, severity: 'medium' },
];

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

function severityBadge(sev) {
  const map = {
    critical: { cls: 'danger',  Icon: ShieldX },
    high:     { cls: 'danger',  Icon: ShieldAlert },
    medium:   { cls: 'warning', Icon: ShieldAlert },
    low:      { cls: 'success', Icon: ShieldCheck },
  };
  return map[sev] || map.low;
}

export default function PolicyEnforcement() {
  const [categoryFilter, setCategoryFilter] = useState('All');
  const categories = useMemo(() => ['All', ...new Set(SEED_POLICIES.map((p) => p.category))], []);

  const filtered = useMemo(() => {
    const rows = categoryFilter === 'All' ? SEED_POLICIES : SEED_POLICIES.filter((p) => p.category === categoryFilter);
    return [...rows].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
  }, [categoryFilter]);

  const totals = useMemo(() => {
    const compliant = SEED_POLICIES.reduce((s, p) => s + p.compliant, 0);
    const noncompliant = SEED_POLICIES.reduce((s, p) => s + p.noncompliant, 0);
    const critical = SEED_POLICIES.filter((p) => p.severity === 'critical' && p.noncompliant > 0).length;
    return { compliant, noncompliant, critical, total: compliant + noncompliant };
  }, []);

  const overallRate = ((totals.compliant / (totals.total || 1)) * 100).toFixed(1);

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <h1 className="page-title icon-inline"><ShieldCheck size={20} /> Policy enforcement</h1>
          <p className="page-subtitle">Governance and cost-guardrail compliance across tagging, SKUs, regions, and network policy.</p>
        </div>
      </div>

      <div className="grid-4" style={{ marginBottom: '1.25rem' }}>
        <div className="stat-card accent">
          <div className="stat-label">Overall compliance</div>
          <div className="stat-value">{overallRate}%</div>
          <div className="stat-sub">{totals.compliant} of {totals.total} resources</div>
        </div>
        <div className="stat-card danger">
          <div className="stat-label">Non-compliant resources</div>
          <div className="stat-value">{totals.noncompliant}</div>
          <div className="stat-sub">Across {SEED_POLICIES.length} policies</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-label">Critical violations</div>
          <div className="stat-value">{totals.critical}</div>
          <div className="stat-sub">Policies with critical severity gaps</div>
        </div>
        <div className="stat-card info">
          <div className="stat-label">Policies tracked</div>
          <div className="stat-value">{SEED_POLICIES.length}</div>
          <div className="stat-sub">{categories.length - 1} categories</div>
        </div>
      </div>

      <div className="toolbar" style={{ marginBottom: '0.85rem' }}>
        <span className="toolbar__label icon-inline"><Filter size={13} /> Category</span>
        {categories.map((c) => (
          <button key={c} type="button" className={`chip${categoryFilter === c ? ' active' : ''}`} onClick={() => setCategoryFilter(c)}>{c}</button>
        ))}
      </div>

      <div className="schedule-list">
        {filtered.map((p) => {
          const { cls, Icon } = severityBadge(p.severity);
          const rate = ((p.compliant / ((p.compliant + p.noncompliant) || 1)) * 100).toFixed(0);
          return (
            <div key={p.id} className="schedule-card">
              <div className="schedule-card__head">
                <Icon size={16} />
                <span className="schedule-card__name">{p.name}</span>
                <span
                  className={`toggle-pill${cls === 'success' ? ' toggle-pill--on' : ''}`}
                  style={
                    cls === 'danger'  ? { background: 'var(--danger-muted)',  color: 'var(--danger-text)' }
                    : cls === 'warning' ? { background: 'var(--warning-muted)', color: 'var(--warning-text)' }
                    : undefined
                  }
                >
                  {p.severity}
                </span>
              </div>
              <div className="schedule-card__body">
                <div className="schedule-card__row"><strong>Category:</strong> {p.category}</div>
                <div className="schedule-card__row"><strong>Scope:</strong> {p.scope}</div>
              </div>
              <div style={{ padding: '0 1rem 0.85rem' }}>
                <div className="score-bar-wrap" style={{ width: '100%' }}>
                  <div className="score-bar" style={{ flex: 1 }}>
                    <div
                      className="score-bar__fill"
                      style={{ width: `${rate}%`, background: Number(rate) >= 95 ? 'var(--success)' : Number(rate) >= 80 ? 'var(--warning)' : 'var(--danger)' }}
                    />
                  </div>
                  <span className="score-bar__label">{rate}%</span>
                </div>
              </div>
              <div className="schedule-card__footer">
                <span>{p.compliant} compliant</span>
                <span>{p.noncompliant} non-compliant</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
