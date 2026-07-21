import React from 'react';

const VARIANTS = {
  primary: 'ds-btn--primary',
  secondary: 'ds-btn--secondary',
  danger: 'ds-btn--danger',
};

const SIZES = {
  small: 'ds-btn--sm',
  medium: 'ds-btn--md',
  large: 'ds-btn--lg',
};

/**
 * Design-system button — Primary / Secondary / Danger, Small / Medium / Large.
 * Renders a native <button> unless `as` is provided (e.g. Link wrapper pattern).
 */
export default function Button({
  variant = 'primary',
  size = 'medium',
  className = '',
  children,
  as: Component = 'button',
  type = 'button',
  ...props
}) {
  const classes = [
    'ds-btn',
    VARIANTS[variant] || VARIANTS.primary,
    SIZES[size] || SIZES.medium,
    className,
  ].filter(Boolean).join(' ');

  if (Component === 'button') {
    return (
      <button type={type} className={classes} {...props}>
        {children}
      </button>
    );
  }

  return (
    <Component className={classes} {...props}>
      {children}
    </Component>
  );
}
