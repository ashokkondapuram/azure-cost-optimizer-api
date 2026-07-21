import React from 'react';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';

export default function RailCollapseButton({ collapsed, onToggle }) {
  return (
    <button
      type="button"
      className="rail-collapse"
      onClick={onToggle}
      aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
      title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
    >
      {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
    </button>
  );
}
