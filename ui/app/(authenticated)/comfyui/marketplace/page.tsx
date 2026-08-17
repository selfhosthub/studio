// ui/app/(authenticated)/comfyui/marketplace/page.tsx

"use client";

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { Upload } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import { useUser } from '@/entities/user';
import { ComfyUIMarketplaceTab } from './components/ComfyUIMarketplaceTab';
import { ComfyUICustomTab } from './components/ComfyUICustomTab';

type ActiveTab = 'marketplace' | 'custom';

function ComfyUIMarketplaceContent() {
  const { user } = useUser();
  const isSuperAdmin = user?.role === 'super_admin';
  const searchParams = useSearchParams();

  // Tab state is owned locally; useSearchParams() isn't reactive across App
  // Router soft navigation, so the URL is mirror-only (shareability).
  const [activeTab, setActiveTab] = useState<ActiveTab | null>(null);
  if (activeTab === null) {
    const fromUrl = searchParams.get('tab') as ActiveTab | null;
    setActiveTab(fromUrl === 'custom' ? 'custom' : 'marketplace');
  }

  useEffect(() => {
    if (activeTab !== null && searchParams.get('tab') !== activeTab) {
      window.history.replaceState(null, '', `/comfyui/marketplace?tab=${activeTab}`);
    }
  }, [activeTab, searchParams]);

  if (!isSuperAdmin) {
    return (
      <>
        <div className="px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-primary">Access Denied</h2>
            <p className="mt-2 text-muted">The ComfyUI marketplace is only available to super admins.</p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
        {/* Header */}
        <div className="mb-8 sm:flex sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-primary">ComfyUI Marketplace</h1>
            <p className="section-subtitle mt-1">Install ComfyUI workflow packages; installed workflows land in the workflows list</p>
          </div>
          {activeTab === 'custom' && (
            <div className="grid grid-flow-col sm:auto-cols-max justify-start sm:justify-end gap-2">
              <Link
                href="/comfyui/upload"
                className="btn-primary inline-flex items-center justify-center gap-2"
              >
                <Upload size={16} />
                Upload Workflow
              </Link>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="border-b border-primary mb-6">
          <nav className="flex space-x-4" aria-label="ComfyUI tabs">
            {(['custom', 'marketplace'] as ActiveTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={`tab capitalize ${activeTab === tab ? 'tab-active' : ''}`}
              >
                {tab}
              </button>
            ))}
          </nav>
        </div>

        {activeTab === 'custom' ? <ComfyUICustomTab /> : <ComfyUIMarketplaceTab />}
      </div>
    </>
  );
}

export default function ComfyUIMarketplacePage() {
  return (
    <Suspense fallback={<><div className="p-8 text-center text-muted">Loading...</div></>}>
      <ComfyUIMarketplaceContent />
    </Suspense>
  );
}
