import React, {
  createContext, useCallback, useContext, useEffect, useMemo,
} from 'react';
import usePersistedState from '../hooks/usePersistedState';

export const THEME_STORAGE_KEY = 'finops-theme';

const ThemeContext = createContext(null);

const THEME_COLORS = {
  light: '#e4f4fc',
  dark: '#121820',
};

function applyTheme(theme) {
  const resolved = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', resolved);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', THEME_COLORS[resolved]);
  return resolved;
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = usePersistedState(THEME_STORAGE_KEY, 'light');

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  }, [setTheme]);

  const value = useMemo(() => ({
    theme: theme === 'dark' ? 'dark' : 'light',
    setTheme,
    toggleTheme,
    isDark: theme === 'dark',
  }), [theme, setTheme, toggleTheme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return ctx;
}
