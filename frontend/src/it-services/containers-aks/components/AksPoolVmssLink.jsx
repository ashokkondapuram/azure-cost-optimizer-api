import React from 'react';
import { Link } from 'react-router-dom';
import { inventoryInspectLink, isArmResourceId } from '../../../utils/armResourceLinks';

export default function AksPoolVmssLink({ vmssId, vmssName, className = '' }) {
  const id = String(vmssId || '').trim();
  const name = String(vmssName || '').trim();
  if (!name && !id) {
    return <span className="insight-drawer__muted">—</span>;
  }

  const inspectLink = isArmResourceId(id) ? inventoryInspectLink(id) : null;
  const label = name || id.split('/').pop();

  if (inspectLink) {
    return (
      <Link
        to={inspectLink}
        className={`aks-pool-vmss-link${className ? ` ${className}` : ''}`}
        title={id || name}
      >
        {label}
      </Link>
    );
  }

  return (
    <span className={`insight-drawer__mono${className ? ` ${className}` : ''}`} title={id || name}>
      {label}
    </span>
  );
}
