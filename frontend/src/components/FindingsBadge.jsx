import React from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { formatCurrency } from '../utils/format';
import { resolveResourceFindings, resolveResourceSavings } from '../utils/resourceFindingsUtils';

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
      <span className="findings-badge findings-badge--clear" title="No open findings">
        <CheckCircle2 size={12} />
        {!compact && 'Clear'}
      </span>
    );
  }

  const critical = resolvedFindings.filter((f) => f.severity === 'CRITICAL').length;
  const high = resolvedFindings.filter((f) => f.severity === 'HIGH').length;
  const medium = resolvedFindings.filter((f) => f.severity === 'MEDIUM').length;
  const tone = critical > 0 ? 'critical' : high > 0 ? 'high' : 'medium';
  const tooltip = `${critical} Critical · ${high} High · ${medium} Medium`;

  return (
    <span
      className={`findings-badge findings-badge--${tone}`}
      data-tooltip={tooltip}
      title={tooltip}
    >
      <AlertTriangle size={12} />
      <span>{resolvedFindings.length}</span>
      {!compact && resolvedSavings > 0 && (
        <span className="findings-badge__savings">
          {formatCurrency(resolvedSavings, { currency, decimals: 0 })}
        </span>
      )}
    </span>
  );
}
