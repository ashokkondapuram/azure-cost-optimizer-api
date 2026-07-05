import React from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, ArrowRight } from 'lucide-react';

export default function FindingResourceLinks({ finding, className = '' }) {
  const {
    resource_app_href: appHref,
    azure_portal_url: portalUrl,
    resource_name: resourceName,
  } = finding || {};

  if (!appHref && !portalUrl) return null;

  return (
    <div className={`finding-resource-links${className ? ` ${className}` : ''}`}>
      {appHref && (
        <Link to={appHref} className="btn btn-ghost btn-sm finding-resource-links__link">
          <ArrowRight size={14} aria-hidden />
          View in inventory
          {resourceName ? ` (${resourceName})` : ''}
        </Link>
      )}
      {portalUrl && (
        <a
          href={portalUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-ghost btn-sm finding-resource-links__link"
        >
          <ExternalLink size={14} aria-hidden />
          Open in Azure
        </a>
      )}
    </div>
  );
}
