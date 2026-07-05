import React from 'react';
import { CheckCircle2, Download, XCircle } from 'lucide-react';

/**
 * Floating bulk action toolbar.
 * Pass custom `actions` or use findings defaults via onResolve/onDismiss/onExport.
 */
export default function BulkActionBar({
  count = 0,
  onResolve,
  onDismiss,
  onExport,
  onClear,
  actions = null,
  resolveDisabled = false,
  dismissDisabled = false,
}) {
  if (count < 1) return null;

  const defaultActions = [];
  if (!resolveDisabled && onResolve) {
    defaultActions.push({
      label: 'Mark resolved',
      icon: CheckCircle2,
      variant: 'primary',
      onClick: onResolve,
    });
  }
  if (onDismiss) {
    defaultActions.push({
      label: 'Mark dismissed',
      icon: XCircle,
      variant: 'secondary',
      onClick: onDismiss,
      disabled: dismissDisabled,
    });
  }
  if (onExport) {
    defaultActions.push({
      label: 'Export selected',
      icon: Download,
      variant: 'ghost',
      onClick: onExport,
    });
  }

  const resolvedActions = (actions || defaultActions).map((action) => ({
    ...action,
    variant: action.variant || 'secondary',
  }));

  return (
    <div className="bulk-action-bar" role="toolbar" aria-label="Bulk actions">
      <span className="bulk-action-bar__count">
        {count.toLocaleString()} selected
      </span>
      <div className="bulk-action-bar__actions">
        {resolvedActions.map((action) => {
          const Icon = action.icon;
          const btnClass = action.variant === 'primary'
            ? 'btn btn-primary btn-sm'
            : action.variant === 'ghost'
              ? 'btn btn-ghost btn-sm'
              : 'btn btn-secondary btn-sm';
          return (
            <button
              key={action.label}
              type="button"
              className={btnClass}
              onClick={action.onClick}
              disabled={action.disabled}
            >
              {Icon && <Icon size={14} aria-hidden />}
              {action.label}
            </button>
          );
        })}
        {onClear && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
            Clear selection
          </button>
        )}
      </div>
    </div>
  );
}
