import React, { useState } from 'react';

export default function BulkAssignModal({
  count,
  onClose,
  onSubmit,
  isPending = false,
}) {
  const [owner, setOwner] = useState('');

  const handleSubmit = (event) => {
    event.preventDefault();
    const trimmed = owner.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  };

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <form
        className="modal-card bulk-tag-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        role="dialog"
        aria-labelledby="bulk-assign-modal-title"
        aria-modal="true"
      >
        <h2 id="bulk-assign-modal-title" className="bulk-tag-modal__title">
          Assign owner to {count} action{count === 1 ? '' : 's'}
        </h2>
        <label className="bulk-tag-modal__field">
          <span>Owner</span>
          <input
            type="text"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            placeholder="team or email"
            required
            autoFocus
          />
        </label>
        <div className="bulk-tag-modal__actions">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={isPending}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={isPending || !owner.trim()}>
            {isPending ? 'Saving…' : 'Assign'}
          </button>
        </div>
      </form>
    </div>
  );
}
