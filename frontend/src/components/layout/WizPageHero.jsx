import React from 'react';
import useSubscriptionLabel from '../../hooks/useSubscriptionLabel';
import { formatPageSubtitle } from '../../utils/subscriptionDisplay';

/**
 * Shared wiz-page hero — title plus subscription-enriched subtitle on every tab.
 */
export default function WizPageHero({
  title,
  pageKey,
  description,
  subtitleSuffix = '',
  actions,
  children,
}) {
  const { subscriptionLabel } = useSubscriptionLabel();
  const subtitle = formatPageSubtitle(pageKey, subscriptionLabel, {
    suffix: subtitleSuffix,
    fallback: description,
  });

  return (
    <header className="wiz-hero">
      <div className="wiz-hero__top">
        <div className="wiz-hero__title-block">
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {actions && (
          <div className="wiz-hero__actions">
            {actions}
          </div>
        )}
      </div>
      {children}
    </header>
  );
}
