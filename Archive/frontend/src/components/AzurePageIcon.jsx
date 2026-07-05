import React from 'react';
import AssetIcon from './AssetIcon';
import { iconForRoute } from '../config/assetIcons';

/** Azure portal icon for a page route or explicit icon key. */
export default function AzurePageIcon({ route, src, size = 28, className = '' }) {
  const iconKey = src || (route != null ? iconForRoute(route) : null);
  if (!iconKey) return null;
  return <AssetIcon iconKey={iconKey} size={size} className={className} />;
}
