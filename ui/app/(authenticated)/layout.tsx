// ui/app/(authenticated)/layout.tsx

import React from 'react';
import { DashboardLayout } from '@/widgets/layout';

// Mounts the dashboard chrome once for every authenticated route.
export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardLayout>{children}</DashboardLayout>;
}
