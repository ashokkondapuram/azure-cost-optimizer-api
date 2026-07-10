/**
 * Gradient hero band for advanced tool pages — matches waste heatmap / tag compliance pattern.
 */
import React from 'react';
import PageHero from '../layout/PageHero';
import { toDisplayText } from '../../utils/formatDisplay';

const VARIANT_BY_ACCENT = {
  savings: 'adv-tool-hero--savings',
  reservations: 'adv-tool-hero--reservations',
  anomaly: 'adv-tool-hero--anomaly',
  ai: 'adv-tool-hero--ai',
  tags: 'adv-tool-hero--tags',
};

const EYEBROW_BY_ACCENT = {
  savings: 'Commitments',
  reservations: 'Reservations',
  anomaly: 'Cost intelligence',
  ai: 'Engine analysis',
  tags: 'Governance',
};

export default function AdvancedToolHero({
  accent,
  eyebrow,
  subtitle,
  scopeNote,
  metrics = [],
  actions = [],
  footer,
  isLoading = false,
  skeletonMetrics = 4,
}) {
  if (!accent && !metrics.length && !footer) return null;

  return (
    <PageHero
      variant={VARIANT_BY_ACCENT[accent] || 'adv-tool-hero'}
      eyebrow={eyebrow || EYEBROW_BY_ACCENT[accent] || 'Insights'}
      subtitle={subtitle ? toDisplayText(subtitle) : undefined}
      scopeNote={scopeNote}
      metrics={metrics}
      actions={actions}
      footer={footer}
      isLoading={isLoading}
      skeletonMetrics={skeletonMetrics}
    />
  );
}

/** Compact footer shell for hero interactive strips (severity, sources, etc.). */
export function AdvHeroFooter({ label, icon: Icon, children }) {
  return (
    <div className="adv-hero__footer">
      <div className="adv-hero__footer-inner">
        {label && (
          <span className="adv-hero__footer-label">
            {Icon && <Icon size={14} aria-hidden />}
            {label}
          </span>
        )}
        {children}
      </div>
    </div>
  );
}
