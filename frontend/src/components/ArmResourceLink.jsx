import React from 'react';
import { ExternalLink } from 'lucide-react';
import {
  azurePortalUrl,
  isArmResourceId,
  shortArmResourceLabel,
} from '../utils/armResourceLinks';

export default function ArmResourceLink({
  resourceId,
  className = '',
  showFullId = false,
}) {
  const value = String(resourceId || '').trim();
  if (!value) return null;

  if (!isArmResourceId(value)) {
    return <span className={className}>{value}</span>;
  }

  const portalUrl = azurePortalUrl(value);
  const label = showFullId ? value : shortArmResourceLabel(value);

  if (!portalUrl) {
    return <span className={className} title={value}>{label}</span>;
  }

  return (
    <a
      href={portalUrl}
      target="_blank"
      rel="noopener noreferrer"
      className={`arm-resource-link${className ? ` ${className}` : ''}`}
      title={value}
    >
      <span className="arm-resource-link__label">{label}</span>
      <ExternalLink size={11} className="arm-resource-link__icon" aria-hidden />
    </a>
  );
}
