import React from 'react';
import {
  DollarSign, Gauge, Shield, Activity, Settings2, Lightbulb,
} from 'lucide-react';

const ICONS = {
  Cost: DollarSign,
  Performance: Gauge,
  HighAvailability: Activity,
  Security: Shield,
  OperationalExcellence: Settings2,
};

export default function AdvisorCategoryIcon({ category, size = 14, className = '' }) {
  const Icon = ICONS[category] || Lightbulb;
  return <Icon size={size} aria-hidden className={className} />;
}
