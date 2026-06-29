// ui/entities/preferences/context.tsx

'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { STORAGE_KEYS } from '@/shared/lib/constants';

// Define the types of preferences we want to store
export interface UserPreferences {
  // Layout preferences
  defaultEditorHeight: number; // Default height of workflow editor in pixels
  sidebarCollapsed: boolean; // Whether the sidebar is collapsed
  editorWidth: 'centered' | 'wide' | 'full'; // Editor content width

  // Visual preferences for flow editor
  nodeSpacing: 'compact' | 'normal' | 'spacious';
  nodeWidth: 'narrow' | 'normal' | 'wide';
  edgeStyle: 'bezier' | 'straight' | 'step';
  backdropBlur: 'none' | 'light' | 'heavy';
  showGrid: boolean;
}

// Default preferences
const defaultPreferences: UserPreferences = {
  defaultEditorHeight: 500,
  sidebarCollapsed: false,
  editorWidth: 'centered',
  nodeSpacing: 'normal',
  nodeWidth: 'normal',
  edgeStyle: 'bezier',
  backdropBlur: 'light',
  showGrid: true,
};

// Create context
type PreferencesContextType = {
  preferences: UserPreferences;
  updatePreference: <K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => void;
  resetPreferences: () => void;
};

const PreferencesContext = createContext<PreferencesContextType | undefined>(undefined);

// Storage key - alias to the central registry entry.
const PREFERENCES_STORAGE_KEY = STORAGE_KEYS.USER_PREFERENCES;

// Provider component
export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const [preferences, setPreferences] = useState<UserPreferences>(defaultPreferences);
  const [loaded, setLoaded] = useState(false);

  // Load preferences from localStorage on first render
  useEffect(() => {
    if (typeof window !== 'undefined') {
      try {
        const savedPreferences = localStorage.getItem(PREFERENCES_STORAGE_KEY);
        if (savedPreferences) {
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setPreferences({
            ...defaultPreferences,
            ...JSON.parse(savedPreferences),
          });
        }
      } catch (error) {
        console.error('Failed to load preferences from localStorage:', error);
      }
      setLoaded(true);
    }
  }, []);

  // Save preferences to localStorage when they change
  useEffect(() => {
    if (loaded && typeof window !== 'undefined') {
      try {
        localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(preferences));
      } catch (error) {
        console.error('Failed to save preferences to localStorage:', error);
      }
    }
  }, [preferences, loaded]);

  // Update a single preference
  const updatePreference = <K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K]
  ) => {
    setPreferences((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  // Reset all preferences to defaults
  const resetPreferences = () => {
    setPreferences(defaultPreferences);
  };

  return (
    <PreferencesContext.Provider
      value={{
        preferences,
        updatePreference,
        resetPreferences,
      }}
    >
      {children}
    </PreferencesContext.Provider>
  );
}

// Hook for using preferences
export function usePreferences() {
  const context = useContext(PreferencesContext);
  if (context === undefined) {
    throw new Error('usePreferences must be used within a PreferencesProvider');
  }
  return context;
}