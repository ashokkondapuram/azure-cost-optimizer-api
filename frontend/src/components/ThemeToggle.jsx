import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

export default function ThemeToggle({ className = '', compact = false }) {
  const { theme, setTheme } = useTheme();
  const isLight = theme === 'light';

  return (
    <div
      className={`theme-toggle${compact ? ' theme-toggle--compact' : ''} ${className}`.trim()}
      role="group"
      aria-label="Color mode"
    >
      <button
        type="button"
        className={isLight ? 'theme-toggle__btn theme-toggle__btn--active' : 'theme-toggle__btn'}
        onClick={() => setTheme('light')}
        aria-pressed={isLight}
        title="Light mode"
      >
        <Sun size={compact ? 14 : 15} aria-hidden />
        {!compact && <span>Light</span>}
      </button>
      <button
        type="button"
        className={!isLight ? 'theme-toggle__btn theme-toggle__btn--active' : 'theme-toggle__btn'}
        onClick={() => setTheme('dark')}
        aria-pressed={!isLight}
        title="Dark mode"
      >
        <Moon size={compact ? 14 : 15} aria-hidden />
        {!compact && <span>Dark</span>}
      </button>
    </div>
  );
}
