import React from 'react';
import { CloudDownload } from 'lucide-react';

/** Fetch the latest inventory from Azure and save it to the database. */
export default function FetchFromAzureButton({
  onClick,
  loading = false,
  disabled = false,
  active = false,
  className = 'btn btn-ghost',
}) {
  return (
    <button
      type="button"
      className={`${className}${active ? ' btn-primary' : ''}`}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading}
      title="Fetch the latest inventory from Azure and save it to the database"
    >
      {loading ? (
        <div className="spin" style={{ width: 14, height: 14, borderWidth: 2 }} />
      ) : (
        <CloudDownload size={13} />
      )}
      {loading ? 'Fetching…' : 'Fetch from Azure'}
    </button>
  );
}
