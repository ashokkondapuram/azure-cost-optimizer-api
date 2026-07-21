import React from 'react';
import { ExternalLink } from 'lucide-react';
import { azurePortalUrl, isArmResourceId } from '../../utils/armResourceLinks';

/** Resource name that opens Azure portal; stops row click propagation. */
export default function WizResourceNameLink({
  resourceId,
  name,
  children,
  className = 'wiz-resource-cell__name-link',
}) {
  const rid = String(resourceId || '').trim();
  const label = children ?? name ?? '—';
  const portalUrl = isArmResourceId(rid) ? azurePortalUrl(rid) : null;

  if (!portalUrl) {
    return <span className={className}>{label}</span>;
  }

  return (
    <a
      href={portalUrl}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
      title={`Open ${name || label} in Azure portal`}
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <span className="wiz-resource-cell__name-link-label">{label}</span>
      <ExternalLink size={11} className="wiz-resource-cell__portal-icon" aria-hidden />
    </a>
  );
}
