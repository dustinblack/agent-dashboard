/**
 * React context for the dashboard theming system.
 *
 * Provides `ThemeProvider` (wrap at the app root) and a
 * `useTheme()` hook that returns the current theme key and
 * a setter.  The selected theme is persisted in localStorage
 * and applied eagerly during initialisation to prevent a
 * flash of the wrong colour scheme (FOUC).
 */

import React, { createContext, useContext, useState, useCallback } from 'react';
import { DEFAULT_THEME, THEMES } from './themeValues';
import type { ThemeKey } from './themeValues';
import { applyTheme } from './applyTheme';

const STORAGE_KEY = 'agent-dashboard-theme';

/** Read stored theme or fall back to default. */
function loadStoredTheme(): ThemeKey {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && stored in THEMES) {
      return stored as ThemeKey;
    }
  } catch {
    // localStorage may be unavailable (e.g. incognito).
  }
  return DEFAULT_THEME;
}

interface ThemeContextValue {
  theme: ThemeKey;
  setTheme: (key: ThemeKey) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: DEFAULT_THEME,
  setTheme: () => {},
});

/**
 * Wrap the application root with this provider to enable
 * theme switching throughout the component tree.
 */
export const ThemeProvider: React.FC<{
  children: React.ReactNode;
}> = ({ children }) => {
  // Lazy initialiser: read localStorage and apply the theme
  // synchronously so the first paint uses the correct palette.
  const [theme, setThemeState] = useState<ThemeKey>(() => {
    const initial = loadStoredTheme();
    applyTheme(initial);
    return initial;
  });

  const setTheme = useCallback((key: ThemeKey) => {
    setThemeState(key);
    applyTheme(key);
    try {
      localStorage.setItem(STORAGE_KEY, key);
    } catch {
      // Silently ignore storage errors.
    }
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

/**
 * Hook to access the current theme and the setter.
 *
 * Must be used within a `<ThemeProvider>`.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
