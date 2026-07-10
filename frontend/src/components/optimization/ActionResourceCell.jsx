import React from 'react';
import ArmResourceLink from '../ArmResourceLink';
import {
  actionResourceDisplayName,
  actionResourceMetaLine,
} from '../../utils/actionUtils';
import { isArmResourceId } from '../../utils/armResourceLinks';

export default function ActionResourceCell({ action, className = '', compact = false }) {
  const title = actionResourceDisplayName(action);
  const meta = actionResourceMetaLine(action);

  if (compact) {
    return (
      <span
        className={`action-resource-cell action-resource-cell--compact${className ? ` ${className}` : ''}`}
        title={meta !== title ? `${meta}` : title}
      >
        {title}
      </span>
    );
  }

  const resourceId = String(action?.resource_id || '').trim();

  return (
    <div className={`cell-stack action-resource-cell${className ? ` ${className}` : ''}`}>
      <strong className="action-resource-cell__name" title={title}>{title}</strong>
      <span className="action-resource-cell__meta text-muted text-sm">{meta}</span>
      {resourceId && isArmResourceId(resourceId) && (
        <ArmResourceLink resourceId={resourceId} className="action-resource-cell__link" />
      )}
    </div>
  );
}
