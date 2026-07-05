import React from 'react';

/**
 * Toggle Azure cost display between billing currency (e.g. CAD) and USD.
 * Both values come from Azure — this only changes which field is shown.
 */
export default function CurrencyToggle({
  value,
  onChange,
  billingCurrency = 'CAD',
  className = '',
}) {
  if (!billingCurrency || billingCurrency === 'USD') {
    return null;
  }

  return (
    <div
      className={`currency-toggle ${className}`.trim()}
      role="group"
      aria-label="Display currency"
    >
      <button
        type="button"
        className={value === billingCurrency ? 'currency-toggle__btn currency-toggle__btn--active' : 'currency-toggle__btn'}
        onClick={() => onChange(billingCurrency)}
        aria-pressed={value === billingCurrency}
      >
        {billingCurrency}
      </button>
      <button
        type="button"
        className={value === 'USD' ? 'currency-toggle__btn currency-toggle__btn--active' : 'currency-toggle__btn'}
        onClick={() => onChange('USD')}
        aria-pressed={value === 'USD'}
      >
        USD
      </button>
    </div>
  );
}
