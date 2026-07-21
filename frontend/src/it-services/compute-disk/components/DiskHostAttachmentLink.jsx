import React from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import ArmResourceLink from '../../../components/ArmResourceLink';

export default function DiskHostAttachmentLink({ attachment, fallbackResourceId = '' }) {
  if (!attachment) {
    return fallbackResourceId
      ? <ArmResourceLink resourceId={fallbackResourceId} />
      : null;
  }

  return (
    <span className="disk-host-attachment">
      {attachment.inventoryLink ? (
        <Link
          to={attachment.inventoryLink}
          className="disk-host-attachment__inventory"
          title={`View ${attachment.typeLabel?.toLowerCase() || 'resource'} in inventory`}
        >
          {attachment.displayLabel}
        </Link>
      ) : (
        <span>{attachment.displayLabel}</span>
      )}
      {attachment.portalLink && (
        <a
          href={attachment.portalLink}
          target="_blank"
          rel="noopener noreferrer"
          className="disk-host-attachment__portal"
          title="Open in Azure portal"
          aria-label={`Open ${attachment.displayLabel} in Azure portal`}
        >
          <ExternalLink size={11} aria-hidden />
        </a>
      )}
    </span>
  );
}
