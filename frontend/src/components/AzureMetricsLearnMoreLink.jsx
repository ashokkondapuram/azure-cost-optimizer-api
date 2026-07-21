import React from 'react';
import { Info } from 'lucide-react';
import { azureMetricsDocUrl } from '../utils/azureMetricsDocs';

export default function AzureMetricsLearnMoreLink({
  docRef,
  docUrl,
  displayName,
  className = '',
  compact = false,
}) {
  const url = docUrl || azureMetricsDocUrl(docRef);
  if (!url) return null;

  const label = displayName
    ? `Learn more about Azure Monitor metrics for ${displayName}`
    : 'Learn more about supported Azure Monitor metrics';

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`azure-metrics-doc-link${compact ? ' azure-metrics-doc-link--compact' : ''} ${className}`.trim()}
      aria-label={label}
      title={label}
      onClick={(event) => event.stopPropagation()}
    >
      <Info size={14} aria-hidden className="azure-metrics-doc-link__icon" />
      {!compact && <span>Learn more</span>}
    </a>
  );
}
