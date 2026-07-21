import React from 'react';
import clsx from 'clsx';

/**
 * Design-system checkbox with token styling.
 */
export default function FormCheckbox({
  id,
  name,
  label,
  checked,
  onChange,
  className,
  hideLabel = false,
  ...rest
}) {
  const inputId = id || name;

  return (
    <label
      className={clsx('form-checkbox', hideLabel && 'form-checkbox--hide-label', className)}
      htmlFor={inputId}
    >
      <input
        id={inputId}
        name={name}
        type="checkbox"
        className="form-checkbox__input"
        checked={checked}
        onChange={onChange}
        {...rest}
      />
      <span className="form-checkbox__control" aria-hidden />
      {label && (
        <span className={clsx('form-checkbox__label', 'text-body-medium')}>
          {label}
        </span>
      )}
    </label>
  );
}
