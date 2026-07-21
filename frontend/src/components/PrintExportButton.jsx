import React from 'react';
import { Printer } from 'lucide-react';

export default function PrintExportButton({ label = 'Export PDF', className = '' }) {
  return (
    <button
      type="button"
      className={`btn btn-ghost btn-sm${className ? ` ${className}` : ''}`}
      onClick={() => window.print()}
    >
      <Printer size={13} aria-hidden />
      {label}
    </button>
  );
}
