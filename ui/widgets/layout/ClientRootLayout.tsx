// ui/widgets/layout/ClientRootLayout.tsx

'use client';

import { UserProvider } from '@/entities/user';
import { PreferencesProvider } from '@/entities/preferences';
import { usePathname } from 'next/navigation';

export default function ClientRootLayout({ children }: { children: React.ReactNode }) {
  return (
    <UserProvider>
      <PreferencesProvider>
        {children}
      </PreferencesProvider>
    </UserProvider>
  );
}