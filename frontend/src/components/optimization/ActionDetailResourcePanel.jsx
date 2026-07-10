import React from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, Search } from 'lucide-react';
import {
  azurePortalUrl,
  inventoryInspectLink,
  isArmResourceId,
} from '../../utils/armResourceLinks';
import {
  actionResourceTypeLabel,
} from '../../utils/actionUtils';
import { resourceGroupLabelForAction } from '../../utils/optimizationGrouping';

function truncateId(value, max = 52) {
  const text = String(value || '').trim();
  if (!text || text.length <= max) return text;
  return `…${text.slice(-max + 1)}`;
}

export default function ActionDetailResourcePanel({ action, layout = 'default' }) {
  const resourceId = String(action?.resource_id || '').trim();
  const resourceGroup = resourceGroupLabelForAction(action);
  const typeLabel = actionResourceTypeLabel(action);
  const portalUrl = isArmResourceId(resourceId) ? azurePortalUrl(resourceId) : null;
  const inspectLink = inventoryInspectLink(resourceId);
  const isModal = layout === 'modal';

  return (
    <section
      className={`action-detail-resource-panel${isModal ? ' action-detail-resource-panel--modal' : ''}`}
      aria-label="Resource details"
    >
      <dl className="action-detail-resource-panel__facts">
        <div className="action-detail-resource-panel__fact">
          <dt>Type</dt>
          <dd>{typeLabel}</dd>
        </div>
        <div className="action-detail-resource-panel__fact">
          <dt>Resource group</dt>
          <dd>{resourceGroup}</dd>
        </div>
      </dl>

      {(portalUrl || inspectLink) && (
        <div className="action-detail-resource-panel__links">
          {portalUrl && (
            <a
              href={portalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="action-detail-link-btn"
            >
              <ExternalLink size={13} aria-hidden />
              Open in Azure
            </a>
          )}
          {inspectLink && (
            <Link to={inspectLink} className="action-detail-link-btn">
              <Search size={13} aria-hidden />
              View in inventory
            </Link>
          )}
        </div>
      )}

      {resourceId && (
        <p className="action-detail-resource-panel__id" title={resourceId}>
          {truncateId(resourceId)}
        </p>
      )}
    </section>
  );
}
