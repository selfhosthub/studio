// ui/app/layout.tsx

'use client';

import 'react-datepicker/dist/react-datepicker.css';
import './globals.css';
import { AuthProvider } from '@/features/auth';
import { UserProvider } from '@/entities/user';
import { PreferencesProvider } from '@/entities/preferences';
import { BrandingProvider } from '@/entities/organization';
import { PageVisibilityProvider } from '@/entities/page-visibility';
import { OrgSettingsProvider } from '@/entities/organization';
import { ToastProvider } from '@/features/toast';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { dashboardColorScript } from '@/shared/lib/dashboard-colors';
import { STORAGE_KEYS } from '@/shared/lib/constants';
import Script from 'next/script';

const queryClient = new QueryClient();

// Script to apply theme on initial page load - runs before React hydration
// Priority: 1) Saved preference, 2) System preference
const themeScript = `
  (function() {
    var saved = localStorage.getItem('${STORAGE_KEYS.THEME_PREFERENCE}');
    if (saved === 'dark') {
      document.documentElement.classList.add('dark');
    } else if (saved === 'light') {
      document.documentElement.classList.remove('dark');
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.classList.add('dark');
    }
  })();
`;

// Global delegated click handler for table row highlighting
const tableRowScript = `
  document.addEventListener('click', function(e) {
    var row = e.target.closest('tbody tr');
    if (!row) return;
    var tbody = row.closest('tbody');
    if (!tbody) return;
    tbody.querySelectorAll('.table-row-active').forEach(function(el) {
      el.classList.remove('table-row-active');
    });
    row.classList.add('table-row-active');
  });
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <Script src="/__env.js" strategy="beforeInteractive" />
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <script dangerouslySetInnerHTML={{ __html: dashboardColorScript }} />
        <script dangerouslySetInnerHTML={{ __html: tableRowScript }} />
      </head>
      <body>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <UserProvider>
              <BrandingProvider>
                <OrgSettingsProvider>
                  <PageVisibilityProvider>
                    <PreferencesProvider>
                      <ToastProvider>
                        {children}
                      </ToastProvider>
                    </PreferencesProvider>
                  </PageVisibilityProvider>
                </OrgSettingsProvider>
              </BrandingProvider>
            </UserProvider>
          </AuthProvider>
        </QueryClientProvider>
      </body>
    </html>
  );
}
