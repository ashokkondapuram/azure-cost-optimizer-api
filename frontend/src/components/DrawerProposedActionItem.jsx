import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import OptimizationActionChip from './optimization/OptimizationActionChip';
import ConfidenceScore from './optimization/ConfidenceScore';
import ActionWorkflowButtons from './optimization/ActionWorkflowButtons';
import ImplementationSteps from './ImplementationSteps';
import { formatCurrency } from '../utils/format';
import { actionTypeLabel } from '../utils/actionUtils';
import { resolveActionImplementationSteps } from '../utils/actionImplementationSteps';
import { resolveActionEvidenceHighlights, resolveActionNarrative } from '../utils/actionNarrativeUtils';
import { actionCentreHubLink } from '../utils/armResourceLinks';
import { toDisplayText } from '../utils/formatDisplay';

export default function DrawerProposedActionItem({
  action,
  findings = [],
  currency = 'CAD',
  subscriptionId,
  isAdmin = false,
  onNavigate,
  embeddedInHub = false,
  onWorkflowUpdated,
}) {
  const steps = useMemo(
    () => resolveActionImplementationSteps(action, findings),
    [action, findings],
  );
  const highlights = useMemo(
    () => resolveActionEvidenceHighlights(action, findings),
    [action, findings],
  );
  const hubLink = action?.resource_id
    ? actionCentreHubLink(action.resource_id, { sectionId: 'actions' })
    : '/action-centre?hasAction=1';

  const savings = Number(action?.estimated_monthly_savings) || 0;
  const reason = resolveActionNarrative(action, findings);

  return (
    <article className="insight-drawer__action-card">
      <header className="insight-drawer__action-card-head">
        <div className="insight-drawer__action-card-title-row">
          <OptimizationActionChip actionType={action.action_type} />
          <ConfidenceScore confidence={action.confidence} compact />
        </div>
        <h4 className="insight-drawer__action-card-title">
          {actionTypeLabel(action.action_type)}
        </h4>
      </header>

      {reason && (
        <p className="insight-drawer__action-card-reason">{reason}</p>
      )}

      {highlights.length > 0 && (
        <dl className="insight-drawer__action-card-evidence">
          {highlights.map((item) => (
            <div key={`${item.label}:${item.value}`} className="insight-drawer__action-card-evidence-item">
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      )}

      <dl className="insight-drawer__action-card-meta">
        {savings > 0 && (
          <div className="insight-drawer__action-card-meta-item">
            <dt>Est. savings</dt>
            <dd>{formatCurrency(savings, { currency, decimals: 0 })}/mo</dd>
          </div>
        )}
        {action.performance_risk && (
          <div className="insight-drawer__action-card-meta-item">
            <dt>Performance risk</dt>
            <dd>{toDisplayText(action.performance_risk)}</dd>
          </div>
        )}
      </dl>

      {steps.length > 0 && (
        <ImplementationSteps
          steps={steps}
          inline
          className="insight-drawer__action-card-steps"
        />
      )}

      <footer className="insight-drawer__action-card-foot">
        <ActionWorkflowButtons
          action={action}
          subscriptionId={subscriptionId}
          isAdmin={isAdmin}
          currency={currency}
          variant="drawer"
          onUpdated={onWorkflowUpdated}
        />
        {!embeddedInHub && (
          <Link
            to={hubLink || '/action-centre?hasAction=1'}
            className="btn btn-ghost btn-sm"
            onClick={onNavigate}
          >
            Open in Action centre
            <ArrowRight size={14} />
          </Link>
        )}
      </footer>
    </article>
  );
}
