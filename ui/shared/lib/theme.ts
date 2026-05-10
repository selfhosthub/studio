// ui/shared/lib/theme.ts

import { STORAGE_KEYS } from './constants';

export const theme = {
  colors: {
    primary: "#3B82F6",
    accent: "#10B981",
    danger: "#EF4444",
    warning: "#F59E0B",

    dark: {
      background: "#111827",
      card: "#1F2937",
      text: "#F9FAFB",
      textSecondary: "#D1D5DB",
      border: "#374151",
    },

    light: {
      background: "#F9FAFB",
      card: "#FFFFFF",
      text: "#111827",
      textSecondary: "#4B5563",
      border: "#E5E7EB",
    },
  },
};

export const THEME_KEY = STORAGE_KEYS.THEME_PREFERENCE;

export const DEFAULT_THEME = 'light';

export const getThemePreference = (): 'light' | 'dark' => {
  if (typeof window === 'undefined') return DEFAULT_THEME as 'light' | 'dark';

  const savedTheme = localStorage.getItem(THEME_KEY);
  if (savedTheme === 'light' || savedTheme === 'dark') {
    return savedTheme;
  }

  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }

  return DEFAULT_THEME as 'light' | 'dark';
};

export const setThemePreference = (theme: 'light' | 'dark'): void => {
  if (typeof window !== 'undefined') {
    localStorage.setItem(THEME_KEY, theme);
  }
};
