import React from 'react';

const TONES = ['success', 'warning', 'danger', 'info'];

/**
 * Design-system badge pill — success / warning / danger / info.
 */
export default function Badge({
  tone = 'info',
  className = '',
  children,
  icon,
  ...props
}) {
  const toneClass = TONES.includes(tone) ? `ds-badge--${tone}` : 'ds-badge--info';
  const classes = ['ds-badge', toneClass, className].filter(Boolean).join(' ');

  return (
    <span className={classes} {...props}>
      {icon}
      {children}
    </span>
  );
}
