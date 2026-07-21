import React from 'react';
import useSubscriptionLabel from '../hooks/useSubscriptionLabel';
import { formatPageSubtitle } from '../utils/subscriptionDisplay';
import AzurePageIcon from './AzurePageIcon';

export default function PageHeader({
  title,
  subtitle,
  pageScope,
  subtitleSuffix = '',
  children,
  badge,
  iconSrc,
  iconKey,
  iconRoute,
}) {
  const { subscriptionLabel } = useSubscriptionLabel();
  const resolvedIcon = iconKey || iconSrc;
  const resolvedSubtitle = pageScope
    ? formatPageSubtitle(pageScope, subscriptionLabel, { suffix: subtitleSuffix, fallback: subtitle })
    : subtitle;

  return (
    <header className="page-header">
      <div className="page-header__text">
        <div className="page-header__title-row">
          {(resolvedIcon || iconRoute != null) && (
            <AzurePageIcon src={resolvedIcon} route={iconRoute} size={28} />
          )}
          <h1 className="page-title">{title}</h1>
          {badge}
        </div>
        {resolvedSubtitle && <p className="page-sub">{resolvedSubtitle}</p>}
      </div>
      {children && <div className="page-header__actions">{children}</div>}
    </header>
  );
}
