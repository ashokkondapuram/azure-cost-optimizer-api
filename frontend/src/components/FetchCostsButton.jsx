import React from 'react';
import { DollarSign } from 'lucide-react';

/** Fetch the latest costs from Azure Cost Management and save them to the database. */
export default function FetchCostsButton({
  onClick,
  loading = false,
  disabled = false,
  className = 'btn btn-ghost',
}) {
  return (
    <button
      type="button"
      className={className}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading}
      title="Fetch the latest cost data from Azure and save it to the database"
    >
      {loading ? (
        <div className="spin" style={{ width: 14, height: 14, borderWidth: 2 }} />
      ) : (
        <DollarSign size={13} />
      )}
      {loading ? 'Fetching…' : 'Fetch costs'}
    </button>
  );
}
