import React from 'react';
import { Zap, Layers } from 'lucide-react';
function WorkflowStat({
  label, value, sub, tone = 'default', icon: Icon, onClick,
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      className={`wiz-stat${onClick ? ' wiz-stat--clickable' : ''}`}
      onClick={onClick}
    >
      <span className={`wiz-stat__icon wiz-stat__icon--${tone}`} aria-hidden>
        <Icon size={16} />
      </span>
      <span>
        <span className="wiz-stat__label">{label}</span>
        <strong className="wiz-stat__value">{value}</strong>
        {sub && <span className="wiz-stat__sub">{sub}</span>}
      </span>
    </Tag>
  );
}

/** Action-centre hero metrics — workflow scope only (no findings summary). */
export default function ActionCentreWorkflowStrip({
  proposedActions = 0,
  proposedResourceCount = 0,
  inventoryTotal = 0,
  onProposedActionsClick,
}) {
  return (
    <div className="wiz-stat-strip action-centre-workflow-strip" aria-label="Action workflow metrics">
      <WorkflowStat
        label="Proposed actions"
        value={proposedActions.toLocaleString()}
        sub={
          proposedResourceCount > 0
            ? `${proposedResourceCount.toLocaleString()} resources awaiting review`
            : 'Awaiting review'
        }
        tone="warning"
        icon={Zap}
        onClick={onProposedActionsClick}
      />
      <WorkflowStat
        label="Synced inventory"
        value={inventoryTotal.toLocaleString()}
        sub="Resources eligible for actions"
        tone="info"
        icon={Layers}
      />
    </div>
  );
}
