import React from 'react';

const TONES = ['default', 'actions', 'findings', 'scoreboard', 'advisor'];

/**
 * Design-system card with 3px top accent bar.
 * Tones: actions, findings, scoreboard, advisor (plus default).
 */
export default function Card({
  tone = 'default',
  clickable = false,
  className = '',
  children,
  as: Component = 'div',
  ...props
}) {
  const toneClass = TONES.includes(tone) ? `ds-card--${tone}` : 'ds-card--default';
  const classes = [
    'ds-card',
    toneClass,
    clickable ? 'ds-card--clickable' : '',
    className,
  ].filter(Boolean).join(' ');

  return (
    <Component className={classes} {...props}>
      {children}
    </Component>
  );
}
