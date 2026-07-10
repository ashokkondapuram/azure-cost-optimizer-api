import React from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import { formatCurrency } from '../../utils/format';
import { toDisplayText } from '../../utils/formatDisplay';
import { inventoryInspectLink } from '../../utils/armResourceLinks';

const SEVERITY_LABEL = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
};

const SAVINGS_SOURCE_LABEL = {
  stored: 'From analysis estimate',
  evidence: 'From finding evidence',
  evidence_cost: 'From resource MTD cost in evidence',
  resource_cost: 'From synced cost data',
  none: 'Not estimated yet',
};

function fmtSavings(amount) {
  const value = Number(amount);
  if (!value || Number.isNaN(value) || value <= 0) return null;
  return formatCurrency(value, { currency: 'USD', decimals: 0 });
}

/**
 * Compact finding summary for the waste heatmap — dashboard context only.
 * Does not load metrics, tags, or the full resource insight drawer.
 */
export default function WasteFindingDetailPanel({ finding, onClose }) {
  if (!finding) return null;

  const severity = String(finding.severity || 'medium').toLowerCase();
  const savings = fmtSavings(finding.estimated_savings_usd);
  const savingsSource = SAVINGS_SOURCE_LABEL[finding.savings_source] || null;
  const resourceGroup = toDisplayText(finding.resource_group);
  const location = toDisplayText(finding.location);
  const inventoryLink = finding.resource_id
    ? inventoryInspectLink(finding.resource_id, { section: 'advanced-analysis' })
    : null;

  return (
    <aside className="waste-finding-panel card" aria-label="Finding summary">
      <header className="waste-finding-panel__head">
        <div>
          <p className="waste-finding-panel__eyebrow">Idle finding</p>
          <h3 className="waste-finding-panel__title">
            {finding.resource_name || finding.resource_id || 'Resource'}
          </h3>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-icon-only"
          onClick={onClose}
          aria-label="Close summary"
        >
          <X size={16} />
        </button>
      </header>

      <div className="waste-finding-panel__body">
        <div className="waste-finding-panel__chips">
          <span className={`waste-severity-pill waste-severity-pill--${severity}`}>
            {SEVERITY_LABEL[severity] || finding.severity}
          </span>
          {finding.category && (
            <span className="waste-finding-panel__chip">{finding.category}</span>
          )}
          {finding.status && (
            <span className="waste-finding-panel__chip waste-finding-panel__chip--muted">
              {finding.status}
            </span>
          )}
        </div>

        <dl className="waste-finding-panel__facts">
          <div className="waste-finding-panel__fact">
            <dt>Est. savings</dt>
            <dd>{savings ?? '—'}</dd>
          </div>
          <div className="waste-finding-panel__fact">
            <dt>Rule</dt>
            <dd title={finding.rule_id}>{finding.title || finding.rule_id || '—'}</dd>
          </div>
          {resourceGroup && (
            <div className="waste-finding-panel__fact">
              <dt>Resource group</dt>
              <dd>{resourceGroup}</dd>
            </div>
          )}
          {location && (
            <div className="waste-finding-panel__fact">
              <dt>Location</dt>
              <dd>{location}</dd>
            </div>
          )}
          {finding.resource_type && (
            <div className="waste-finding-panel__fact">
              <dt>Type</dt>
              <dd className="waste-finding-panel__mono">{finding.resource_type}</dd>
            </div>
          )}
        </dl>

        {finding.detail && (
          <section className="waste-finding-panel__section">
            <h4>What we found</h4>
            <p>{finding.detail}</p>
          </section>
        )}

        {finding.recommendation && (
          <section className="waste-finding-panel__section waste-finding-panel__section--action">
            <h4>Recommended action</h4>
            <p>{finding.recommendation}</p>
          </section>
        )}

        {savingsSource && (
          <p className="waste-finding-panel__note">{savingsSource}</p>
        )}
      </div>

      <footer className="waste-finding-panel__foot">
        <Link to="/optimization-hub?tab=actions" className="btn btn-secondary btn-sm">
          Review in hub
        </Link>
        {inventoryLink ? (
          <Link to={inventoryLink} className="btn btn-secondary btn-sm">
            View advanced analysis
          </Link>
        ) : (
          <span className="text-muted text-sm">No inventory page for this resource type.</span>
        )}
      </footer>
    </aside>
  );
}
