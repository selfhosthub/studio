// ui/app/ai-agents/layout.tsx

import React from 'react';
import { DashboardLayout } from '@/widgets/layout';

export default function AIAgentsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardLayout>{children}</DashboardLayout>;
}
