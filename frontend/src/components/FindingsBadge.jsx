import React from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { formatCurrency } from '../utils/format';
import { resolveResourceFindings, resolveResourceSavings } from '../utils/resourceFindingsUtils';
import Badge from './Badge';

const TONE_MAP = {
  critical: 'danger',
  high: 'warning',
  medium: 'info',
};

export default function FindingsBadge({
  findings = [],
  resource = null,
  indexFindings = null,
  savings = 0,
  currency = 'CAD',
  compact = false,
  indexReady = false,
}) {
  const options = { indexReady };
  const resolvedFindings = resource
    ? resolveResourceFindings(resource, indexFindings ?? [], options)
    : findings;
  const resolvedSavings = resource
    ? resolveResourceSavings(resource, indexFindings ?? [], savings, options)
    : savings;

  if (!resolvedFindings.length) {
    return (
      <Badge tone="success" icon={<CheckCircle2 size={12} />} title="No open findings">
        {!compact && 'Clear'}
      </Badge>
    );
  }

  const critical = resolvedFindings.filter((f) => f.severity === 'CRITICAL').length;
  const high = resolvedFindings.filter((f) => f.severity === 'HIGH').length;
  const medium = resolvedFindings.filter((f) => f.severity === 'MEDIUM').length;
  const severity = critical > 0 ? 'critical' : high > 0 ? 'high' : 'medium';
  const tone = TONE_MAP[severity];
  const tooltip = `${critical} Critical · ${high} High · ${medium} Medium`;

  return (
    <Badge
      tone={tone}
      icon={<AlertTriangle size={12} />}
      data-tooltip={tooltip}
      title={tooltip}
    >
      <span>{resolvedFindings.length}</span>
      {!compact && resolvedSavings > 0 && (
        <span className="findings-badge__savings">
          {formatCurrency(resolvedSavings, { currency, decimals: 0 })}
        </span>
      )}
    </Badge>
  );
}
