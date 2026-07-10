import React from 'react';
import {
  DollarSign, Shield, Activity, Server, Boxes, HardDrive, Network, Database, Settings2, Lightbulb,
} from 'lucide-react';

const ICONS = {
  COST: DollarSign,
  RELIABILITY: Activity,
  SECURITY: Shield,
  COMPUTE: Server,
  KUBERNETES: Boxes,
  STORAGE: HardDrive,
  NETWORK: Network,
  DATABASE: Database,
  GOVERNANCE: Settings2,
};

export default function FindingCategoryIcon({ category, size = 14, className = '' }) {
  const key = String(category || '').toUpperCase();
  const Icon = ICONS[key] || Lightbulb;
  return <Icon size={size} aria-hidden className={className} />;
}
