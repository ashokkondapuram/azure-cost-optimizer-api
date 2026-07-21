import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle2, ExternalLink, Loader2, X, XCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { addSubscription, validateSubscriptionAccess } from '../../api/azure';
import { getErrorMessage } from '../../api/errors';

const GUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function authModeLabel(mode) {
  if (!mode) return 'Azure credential';
  return mode.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function ValidationBanner({ result }) {
  if (!result) return null;
  const isSuccess = Boolean(result.valid ?? result.connected);
  const Icon = isSuccess ? CheckCircle2 : XCircle;
  return (
    <div className={`add-sub-modal__banner add-sub-modal__banner--${isSuccess ? 'success' : 'error'}`} role="status">
      <Icon size={16} className="add-sub-modal__banner-icon" aria-hidden />
      <div className="add-sub-modal__banner-body">
        <p className="add-sub-modal__banner-message">{result.message || result.error}</p>
        {result.validation_method && (
          <p className="add-sub-modal__banner-meta text-muted text-sm">
            Validated via {result.validation_method === 'azure_cli' ? 'Azure CLI' : 'Azure API'}
          </p>
        )}
        {result.auth_mode && (
          <p className="add-sub-modal__banner-meta text-muted text-sm">
            Auth mode: {authModeLabel(result.auth_mode)}
            {result.state ? ` · State: ${result.state}` : ''}
            {result.tenant_id ? ` · Tenant: ${result.tenant_id}` : ''}
          </p>
        )}
        {!isSuccess && ['auth_failed', 'forbidden', 'tenant_mismatch', 'creds_missing'].includes(result.error_code) && (
          <Link to="/settings?tab=azure" className="add-sub-modal__settings-link">
            Open Azure connection settings
            <ExternalLink size={12} aria-hidden />
          </Link>
        )}
      </div>
    </div>
  );
}

export default function AddSubscriptionModal({
  open,
  onClose,
  onAdded,
  hasExistingSubscriptions = false,
}) {
  const [subscriptionId, setSubscriptionId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [setAsDefault, setSetAsDefault] = useState(!hasExistingSubscriptions);
  const [validation, setValidation] = useState(null);
  const firstFieldRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    setSubscriptionId('');
    setDisplayName('');
    setSetAsDefault(!hasExistingSubscriptions);
    setValidation(null);
    const timer = window.setTimeout(() => firstFieldRef.current?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [open, hasExistingSubscriptions]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  const validateMut = useMutation({
    mutationFn: () => validateSubscriptionAccess({
      subscription_id: subscriptionId.trim(),
    }),
    onSuccess: (result) => {
      setValidation(result);
      if ((result.valid ?? result.connected) && result.display_name && !displayName.trim()) {
        setDisplayName(result.display_name);
      }
    },
    onError: (err) => {
      setValidation({
        connected: false,
        message: getErrorMessage(err, 'Validation failed.'),
        error_code: 'request_failed',
      });
    },
  });

  const addMut = useMutation({
    mutationFn: () => addSubscription({
      subscription_id: subscriptionId.trim(),
      display_name: displayName.trim() || undefined,
      set_as_default: setAsDefault,
    }),
    onSuccess: (result) => {
      onAdded?.(result);
      onClose();
    },
  });

  if (!open) return null;

  const trimmedId = subscriptionId.trim();
  const idValid = GUID_RE.test(trimmedId);
  const canValidate = idValid && !validateMut.isPending;
  const canAdd = (validation?.valid ?? validation?.connected) && !addMut.isPending;

  const handleValidate = (event) => {
    event.preventDefault();
    if (!canValidate) return;
    setValidation(null);
    validateMut.mutate();
  };

  const handleAdd = (event) => {
    event.preventDefault();
    if (!canAdd) return;
    addMut.mutate();
  };

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <form
        className="modal-card add-sub-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleAdd}
        role="dialog"
        aria-labelledby="add-sub-modal-title"
        aria-modal="true"
      >
        <header className="add-sub-modal__header">
          <div>
            <h2 id="add-sub-modal-title" className="add-sub-modal__title">Add subscription</h2>
            <p className="add-sub-modal__subtitle text-muted text-sm">
              Validate that your Azure credentials can access a subscription, then add it to the sidebar.
            </p>
          </div>
          <button type="button" className="add-sub-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>

        <label className="add-sub-modal__field">
          <span>Subscription ID</span>
          <input
            ref={firstFieldRef}
            type="text"
            value={subscriptionId}
            onChange={(e) => {
              setSubscriptionId(e.target.value);
              setValidation(null);
            }}
            placeholder="00000000-0000-0000-0000-000000000000"
            autoComplete="off"
            spellCheck={false}
          />
          {trimmedId && !idValid && (
            <span className="add-sub-modal__field-error">Enter a valid subscription GUID.</span>
          )}
        </label>

        <label className="add-sub-modal__field">
          <span>Display name <span className="text-muted">(optional)</span></span>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Production subscription"
            autoComplete="off"
          />
        </label>

        <label className="add-sub-modal__checkbox">
          <input
            type="checkbox"
            checked={setAsDefault}
            onChange={(e) => setSetAsDefault(e.target.checked)}
          />
          <span>Set as default subscription</span>
        </label>

        <ValidationBanner result={validation} />

        {addMut.isError && (
          <div className="add-sub-modal__banner add-sub-modal__banner--error" role="alert">
            <XCircle size={16} className="add-sub-modal__banner-icon" aria-hidden />
            <p className="add-sub-modal__banner-message">
              {getErrorMessage(addMut.error, 'Could not add subscription.')}
            </p>
          </div>
        )}

        <div className="add-sub-modal__actions">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={addMut.isPending}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleValidate}
            disabled={!canValidate}
          >
            {validateMut.isPending ? (
              <>
                <Loader2 size={14} className="spin" aria-hidden />
                Validating…
              </>
            ) : (
              'Validate access'
            )}
          </button>
          <button type="submit" className="btn btn-primary" disabled={!canAdd}>
            {addMut.isPending ? 'Adding…' : 'Add subscription'}
          </button>
        </div>
      </form>
    </div>
  );
}
