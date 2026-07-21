import React from 'react';
import clsx from 'clsx';

/**
 * Design-system text input with token styling.
 */
export default function FormInput({
  id,
  name,
  label,
  type = 'text',
  value,
  onChange,
  placeholder,
  className,
  inputClassName,
  hideLabel = false,
  ...rest
}) {
  const inputId = id || name;

  return (
    <label
      className={clsx('form-field', hideLabel && 'form-field--hide-label', className)}
      htmlFor={inputId}
    >
      {label && (
        <span className={clsx('form-field__label', 'text-label')}>
          {label}
        </span>
      )}
      <input
        id={inputId}
        name={name}
        type={type}
        className={clsx('form-input', inputClassName)}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        {...rest}
      />
    </label>
  );
}
