import React from 'react';
import { Menu, X } from 'lucide-react';
import AssetIcon from './AssetIcon';

export default function MobileHeader({ open, onToggle, title, iconKey }) {
  return (
    <header className="mobile-header">
      <button
        type="button"
        className="mobile-header__menu"
        onClick={onToggle}
        aria-expanded={open}
        aria-label={open ? 'Close menu' : 'Open menu'}
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>
      {iconKey && <AssetIcon iconKey={iconKey} size={22} className="mobile-header__icon" />}
      <span className="mobile-header__title">{title}</span>
    </header>
  );
}
