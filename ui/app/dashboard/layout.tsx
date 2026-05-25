// ui/app/dashboard/layout.tsx


"use client";

import React, { useEffect } from 'react';
import { getThemePreference } from '@/shared/lib/theme';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Apply dark mode class on component mount
  useEffect(() => {
    const savedTheme = getThemePreference();
    if (savedTheme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }

    // Listen for storage events to sync theme across tabs
    const handleStorageChange = () => {
      const updatedTheme = getThemePreference();
      if (updatedTheme === 'dark') {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  return <>{children}</>;
}
