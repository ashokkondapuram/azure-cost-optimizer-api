import React, { useState } from 'react';

export default function BulkTagModal({
  count,
  onClose,
  onSubmit,
  isPending = false,
}) {
  const [key, setKey] = useState('');
  const [value, setValue] = useState('');

  const handleSubmit = (event) => {
    event.preventDefault();
    const trimmedKey = key.trim();
    if (!trimmedKey) return;
    onSubmit({ [trimmedKey]: value.trim() });
  };

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <form
        className="modal-card bulk-tag-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        role="dialog"
        aria-labelledby="bulk-tag-modal-title"
        aria-modal="true"
      >
        <h2 id="bulk-tag-modal-title" className="bulk-tag-modal__title">
          Add tag to {count} resource{count === 1 ? '' : 's'}
        </h2>
        <p className="text-muted text-sm">Tags are applied in Azure and saved to inventory.</p>
        <label className="bulk-tag-modal__field">
          <span>Key</span>
          <input
            type="text"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="environment"
            required
            autoFocus
          />
        </label>
        <label className="bulk-tag-modal__field">
          <span>Value</span>
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="production"
          />
        </label>
        <div className="bulk-tag-modal__actions">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={isPending}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={isPending || !key.trim()}>
            {isPending ? 'Saving…' : 'Apply tag'}
          </button>
        </div>
      </form>
    </div>
  );
}
