import React, { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { toDisplayText } from '../utils/formatDisplay';

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

function ToastItem({ toast, onDismiss }) {
  const [remaining, setRemaining] = useState(toast.countdown || 0);

  useEffect(() => {
    if (!toast.countdown) return undefined;
    setRemaining(toast.countdown);
    const started = Date.now();
    const interval = window.setInterval(() => {
      const elapsed = Date.now() - started;
      const left = Math.max(0, toast.countdown - elapsed);
      setRemaining(left);
      if (left <= 0) window.clearInterval(interval);
    }, 200);
    return () => window.clearInterval(interval);
  }, [toast.countdown, toast.id]);

  const Icon = ICONS[toast.variant] || Info;

  return (
    <div
      className={`toast toast--${toast.variant || 'info'}`}
      role="status"
    >
      <Icon size={18} className="toast__icon" aria-hidden />
      <div className="toast__body">
        <p className="toast__message">{toDisplayText(toast.message)}</p>
        {toast.countdown > 0 && (
          <p className="toast__countdown">
            {Math.ceil(remaining / 1000)}s
          </p>
        )}
      </div>
      {toast.onAction && (
        <button
          type="button"
          className="toast__action"
          onClick={toast.onAction}
        >
          {toast.actionLabel || 'Undo'}
        </button>
      )}
      <button
        type="button"
        className="toast__close"
        onClick={() => onDismiss(toast.id)}
        aria-label="Close"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export default function ToastContainer({ toasts, onDismiss }) {
  if (!toasts?.length) return null;

  return (
    <div className="toast-stack" role="region" aria-label="Notifications" aria-live="polite">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
