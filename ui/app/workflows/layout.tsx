// ui/app/workflows/layout.tsx

import React from 'react';
import { DashboardLayout } from '@/widgets/layout';

export default function WorkflowsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardLayout>{children}</DashboardLayout>;
}