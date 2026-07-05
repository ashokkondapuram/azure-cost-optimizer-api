import React from 'react';
import { AlertOctagon, AlertTriangle, CircleAlert, Info } from 'lucide-react';

const SEVERITY_CHIP = {
  CRITICAL: { icon: AlertOctagon, mod: 'critical' },
  HIGH: { icon: AlertTriangle, mod: 'high' },
  MEDIUM: { icon: CircleAlert, mod: 'medium' },
  LOW: { icon: Info, mod: 'low' },
  INFO: { icon: Info, mod: 'info' },
};

export function severityAccentClass(severity) {
  const mod = (severity || 'MEDIUM').toUpperCase();
  return `rec-detail-card--sev-${(SEVERITY_CHIP[mod] || SEVERITY_CHIP.MEDIUM).mod}`;
}

export default function SeverityChip({ severity, size = 12 }) {
  const key = (severity || 'INFO').toUpperCase();
  const meta = SEVERITY_CHIP[key] || SEVERITY_CHIP.INFO;
  const Icon = meta.icon;
  return (
    <span className={`severity-chip severity-chip--${meta.mod}`}>
      <Icon size={size} aria-hidden />
      {key}
    </span>
  );
}
