import React from 'react';
import { formatCurrency } from '../../utils/format';

export default function DashboardSummary({
  inventoryTotal,
  openFindings,
  estSavings,
  criticalCount,
  highCount,
  currency,
}) {
  return (
    <section className="dashboard-summary">
      <div className="dashboard-summary__hero">
        <div className="dashboard-summary__copy">
          <p className="dashboard-summary__eyebrow">Subscription overview</p>
          <h2 className="dashboard-summary__title">
            {inventoryTotal.toLocaleString()} resources in synced inventory
          </h2>
          <p className="dashboard-summary__sub">
            {openFindings.toLocaleString()} engine signals merged into optimization actions
          </p>
        </div>
        <div className="dashboard-summary__kpis">
          <div className="dashboard-summary__kpi dashboard-summary__kpi--success">
            <span className="dashboard-summary__kpi-value">
              {formatCurrency(estSavings, { currency, decimals: 0 })}
            </span>
            <span className="dashboard-summary__kpi-label">Est. monthly savings</span>
          </div>
          <div className="dashboard-summary__kpi dashboard-summary__kpi--danger">
            <span className="dashboard-summary__kpi-value">{criticalCount}</span>
            <span className="dashboard-summary__kpi-label">Critical</span>
          </div>
          <div className="dashboard-summary__kpi dashboard-summary__kpi--warning">
            <span className="dashboard-summary__kpi-value">{highCount}</span>
            <span className="dashboard-summary__kpi-label">High</span>
          </div>
          <div className="dashboard-summary__kpi">
            <span className="dashboard-summary__kpi-value">{openFindings.toLocaleString()}</span>
            <span className="dashboard-summary__kpi-label">Open total</span>
          </div>
        </div>
      </div>
    </section>
  );
}
