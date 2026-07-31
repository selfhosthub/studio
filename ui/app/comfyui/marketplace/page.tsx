// ui/app/comfyui/marketplace/page.tsx

"use client";

import { Suspense } from 'react';
import { DashboardLayout } from '@/widgets/layout';
import { useUser } from '@/entities/user';
import { isComfyUIMarketplaceEnabled } from '@/shared/lib/config';
import { ComfyUIMarketplaceTab } from './components/ComfyUIMarketplaceTab';

function ComfyUIMarketplaceContent() {
  const { user } = useUser();
  const isSuperAdmin = user?.role === 'super_admin';

  if (!isSuperAdmin || !isComfyUIMarketplaceEnabled()) {
    return (
      <DashboardLayout>
        <div className="px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-primary">Access Denied</h2>
            <p className="mt-2 text-muted">The ComfyUI marketplace is only available to super admins.</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-primary">ComfyUI Marketplace</h1>
          <p className="text-sm mt-1 text-muted">Install ComfyUI workflow packages; installed workflows land in the workflows list</p>
        </div>

        <ComfyUIMarketplaceTab />
      </div>
    </DashboardLayout>
  );
}

export default function ComfyUIMarketplacePage() {
  return (
    <Suspense fallback={<DashboardLayout><div className="p-8 text-center text-muted">Loading...</div></DashboardLayout>}>
      <ComfyUIMarketplaceContent />
    </Suspense>
  );
}
