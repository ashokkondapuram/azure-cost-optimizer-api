import React from 'react';
import {
  AlertTriangle, Boxes, Cloud, DollarSign, Layers, Shield,
} from 'lucide-react';
import { formatCurrency } from '../../utils/format';
import {
  openFindingsCount,
  totalEstimatedSavings,
  resourcesWithFindings,
} from '../../utils/findingsSummaryUtils';
import { OpenIssuesSubline } from './WizSourceBreakdown';

function WizStat({
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

export default function WizStatStrip({
  summary,
  inventoryTotal,
  serviceCount,
  proposedActions,
  assessmentFiles,
  currency,
  onTab,
  onProposedActionsClick,
  proposedResourceCount,
}) {
  const open = openFindingsCount(summary);
  const savings = totalEstimatedSavings(summary);
  const critical = summary?.by_severity?.CRITICAL ?? summary?.severity?.CRITICAL ?? 0;
  const high = summary?.by_severity?.HIGH ?? summary?.severity?.HIGH ?? 0;
  const resources = resourcesWithFindings(summary);
  const sourceSub = <OpenIssuesSubline summary={summary} />;
  const urgencySub = critical + high > 0 ? `${critical + high} critical or high` : 'No urgent issues';
  const openSub = sourceSub || (resources > 0 ? `${resources.toLocaleString()} resources` : urgencySub);

  return (
    <div className="wiz-stat-strip">
      <WizStat
        label="Open issues"
        value={open.toLocaleString()}
        sub={open > 0 ? openSub : urgencySub}
        tone="critical"
        icon={AlertTriangle}
        onClick={() => onTab?.('issues')}
      />
      <WizStat
        label="Est. savings/mo"
        value={formatCurrency(savings, { currency, decimals: 0 })}
        sub="From open findings"
        tone="success"
        icon={DollarSign}
        onClick={() => onTab?.('issues')}
      />
      <WizStat
        label="Billed resources"
        value={(inventoryTotal ?? 0).toLocaleString()}
        sub="MTD cost inventory"
        tone="info"
        icon={Boxes}
        onClick={() => onTab?.('inventory')}
      />
      <WizStat
        label={proposedActions != null ? 'Proposed actions' : 'IT services'}
        value={(proposedActions ?? serviceCount ?? 0).toLocaleString()}
        sub={
          proposedActions != null
            ? (
              proposedResourceCount != null && proposedResourceCount > 0
                ? `${proposedResourceCount.toLocaleString()} resources awaiting review`
                : 'Awaiting review'
            )
            : (assessmentFiles ? `${assessmentFiles} assessment files` : 'Engine catalog')
        }
        tone="default"
        icon={Layers}
        onClick={
          onProposedActionsClick
          ?? (onTab ? () => onTab(proposedActions != null ? 'issues' : 'services') : undefined)
        }
      />
      <WizStat
        label="Coverage"
        value={assessmentFiles ? `${assessmentFiles}` : '—'}
        sub="Indexed ARM assessments"
        tone="default"
        icon={Shield}
        onClick={() => onTab?.('pipeline')}
      />
      <WizStat
        label="Cloud scope"
        value="Azure"
        sub="Unified explorer"
        tone="info"
        icon={Cloud}
      />
    </div>
  );
}
