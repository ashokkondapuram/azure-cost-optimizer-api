import React from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, ArrowRight } from 'lucide-react';
import { resolveResourceAppHref } from '../utils/armResourceLinks';

export default function FindingResourceLinks({ finding, className = '' }) {
  const appHref = resolveResourceAppHref(finding);
  const portalUrl = finding?.azure_portal_url;
  const resourceName = finding?.resource_name;

  if (!appHref && !portalUrl) return null;

  return (
    <div className={`finding-resource-links${className ? ` ${className}` : ''}`}>
      {appHref && (
        <Link to={appHref} className="btn btn-ghost btn-sm finding-resource-links__link">
          <ArrowRight size={14} aria-hidden />
          Open in action centre
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
