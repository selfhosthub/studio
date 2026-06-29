// ui/widgets/layout/DarkModeToggle.tsx


'use client';

import { useSyncExternalStore } from 'react';
import { Sun, Moon } from 'lucide-react';
import { getThemePreference, setThemePreference } from '@/shared/lib/theme';

function getDocumentTheme(): 'light' | 'dark' {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

function applyThemeFromStorage() {
  const saved = getThemePreference();
  if (saved === 'dark') {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
}

const themeSubscribe = (callback: () => void) => {
  const handleStorage = () => {
    applyThemeFromStorage();
    callback();
  };
  window.addEventListener('storage', handleStorage);
  window.addEventListener('theme-change', callback);
  return () => {
    window.removeEventListener('storage', handleStorage);
    window.removeEventListener('theme-change', callback);
  };
};

export default function DarkModeToggle() {
  const theme = useSyncExternalStore(themeSubscribe, getDocumentTheme, () => 'light' as const);

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setThemePreference(newTheme);

    // Apply theme to document
    if (newTheme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }

    // Dispatch storage event to notify other components
    window.dispatchEvent(new Event('storage'));

    // Dispatch custom theme-change event for components within the same window
    window.dispatchEvent(new CustomEvent('theme-change', { detail: { theme: newTheme } }));
  };

  return (
    <button
      onClick={toggleTheme}
      className="p-2 rounded-full transition-opacity opacity-80 hover:opacity-100 text-info"
      aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {theme === 'dark' ? (
        <Sun size={20} />
      ) : (
        <Moon size={20} />
      )}
    </button>
  );
}
