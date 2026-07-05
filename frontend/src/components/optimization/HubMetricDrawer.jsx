import React from 'react';
import { X } from 'lucide-react';
import { formatCurrency } from '../../utils/format';

export default function HubMetricDrawer({ open, title, subtitle, onClose, children }) {
  if (!open) return null;

  return (
    <div className="hub-metric-drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="hub-metric-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="hub-metric-drawer-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="hub-metric-drawer__head">
          <div>
            <h3 id="hub-metric-drawer-title">{title}</h3>
            {subtitle && <p className="hub-metric-drawer__sub">{subtitle}</p>}
          </div>
          <button type="button" className="btn btn-ghost btn-icon-only" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </header>
        <div className="hub-metric-drawer__body">{children}</div>
      </aside>
    </div>
  );
}

export function HubMetricRow({ label, value, tone }) {
  return (
    <div className={`hub-metric-row${tone ? ` hub-metric-row--${tone}` : ''}`}>
      <span className="hub-metric-row__label">{label}</span>
      <strong className="hub-metric-row__value">{value}</strong>
    </div>
  );
}

export function HubSeverityBars({ bySeverity = {}, currency, savingsBySeverity }) {
  const order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
  const total = order.reduce((n, k) => n + (bySeverity[k] || 0), 0) || 1;

  return (
    <div className="hub-severity-bars">
      {order.filter((k) => (bySeverity[k] || 0) > 0).map((sev) => {
        const count = bySeverity[sev] || 0;
        const pct = Math.round((count / total) * 100);
        const savings = savingsBySeverity?.[sev];
        return (
          <div key={sev} className={`hub-severity-bars__row hub-severity-bars__row--${sev.toLowerCase()}`}>
            <div className="hub-severity-bars__head">
              <span>{sev.charAt(0) + sev.slice(1).toLowerCase()}</span>
              <span>{count.toLocaleString()} · {pct}%</span>
            </div>
            <div className="hub-severity-bars__track">
              <div className="hub-severity-bars__fill" style={{ width: `${pct}%` }} />
            </div>
            {savings != null && savings > 0 && (
              <span className="hub-severity-bars__savings">
                {formatCurrency(savings, { currency, decimals: 0 })}/mo
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
