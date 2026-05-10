// ui/app/blueprints/layout.tsx

import React from 'react';
import { DashboardLayout } from '@/widgets/layout';

export default function BlueprintsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardLayout>{children}</DashboardLayout>;
}
