import React, {
  createContext, useContext, useEffect, useMemo,
} from 'react';

export const THEME_STORAGE_KEY = 'finops-theme';
const FORCED_THEME = 'dark';
const THEME_COLOR = '#030f41';

const ThemeContext = createContext(null);

function applyTheme() {
  document.documentElement.setAttribute('data-theme', FORCED_THEME);
  document.documentElement.style.colorScheme = 'dark';
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', THEME_COLOR);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(FORCED_THEME));
  } catch {
    /* ignore quota / private mode */
  }
}

export function ThemeProvider({ children }) {
  useEffect(() => {
    applyTheme();
  }, []);

  const value = useMemo(() => ({
    theme: FORCED_THEME,
    isDark: true,
  }), []);

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
