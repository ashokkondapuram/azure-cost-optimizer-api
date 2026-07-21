import React from 'react';
import { getIconComponent, resolveIconKey } from '../config/azureIconRegistry';

/**
 * Renders an open-source Azure Architecture icon (react-az-icons).
 * Accepts logical iconKey, legacy src paths, or ARM/category context.
 */
export default function AssetIcon({
  src,
  iconKey,
  armType,
  category,
  component,
  route,
  apiPath,
  resourceId,
  size = 18,
  alt = '',
  className = '',
  style = {},
  fallback = null,
}) {
  const key = resolveIconKey({
    iconKey,
    src,
    armType,
    category,
    component,
    route,
    apiPath,
    resourceId,
  });

  const Icon = key ? getIconComponent(key) : null;

  if (!Icon) {
    return fallback || null;
  }

  return (
    <span
      className={`azure-service-icon ${className}`.trim()}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        flexShrink: 0,
        lineHeight: 0,
        ...style,
      }}
      role={alt ? 'img' : undefined}
      aria-label={alt || undefined}
      aria-hidden={!alt ? true : undefined}
    >
      <Icon size={String(size)} />
    </span>
  );
}
