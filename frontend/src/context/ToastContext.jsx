import React, {
  createContext, useCallback, useContext, useMemo, useRef, useState,
} from 'react';
import ToastContainer from '../components/ToastContainer';

const ToastCtx = createContext(null);

let toastCounter = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timersRef = useRef(new Map());

  const dismiss = useCallback((id) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      window.clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback((message, options = {}) => {
    const text = message == null ? '' : String(message).trim();
    if (!text) return null;

    const id = `toast-${Date.now()}-${toastCounter += 1}`;
    const variant = options.variant || 'info';
    const duration = options.duration ?? 6000;

    setToasts((prev) => [...prev, {
      id,
      message: text,
      variant,
      actionLabel: options.actionLabel,
      onAction: options.onAction,
      countdown: options.countdown,
    }]);

    if (duration > 0) {
      const timer = window.setTimeout(() => dismiss(id), duration);
      timersRef.current.set(id, timer);
    }
    return id;
  }, [dismiss]);

  const showUndoToast = useCallback((message, onUndo, options = {}) => {
    const duration = options.duration ?? 5000;
    const id = showToast(message, {
      variant: options.variant || 'info',
      duration,
      actionLabel: options.actionLabel || 'Undo',
      onAction: () => {
        onUndo?.();
        dismiss(id);
      },
      countdown: duration,
    });
    return id;
  }, [dismiss, showToast]);

  const value = useMemo(
    () => ({ showToast, showUndoToast, dismiss }),
    [showToast, showUndoToast, dismiss],
  );

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) {
    return { showToast: () => null, showUndoToast: () => null, dismiss: () => {} };
  }
  return ctx;
}
