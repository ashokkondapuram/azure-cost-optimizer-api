import React from 'react';
import { AzureResourceIcon } from './FinOpsIcons';

/** Azure service icon (open-source react-az-icons). */
export default function AzureIcon({ type, size = 28, style = {} }) {
  return (
    <span style={{ display: 'inline-flex', flexShrink: 0, ...style }}>
      <AzureResourceIcon type={type} size={size} />
    </span>
  );
}
