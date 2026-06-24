import React from 'react';
import AzurePageIcon from './AzurePageIcon';

export default function PageHeader({ title, subtitle, children, badge, iconSrc, iconKey, iconRoute }) {
  const resolvedIcon = iconKey || iconSrc;
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
        {subtitle && <p className="page-sub">{subtitle}</p>}
      </div>
      {children && <div className="page-header__actions">{children}</div>}
    </header>
  );
}
