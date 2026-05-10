// ui/app/organization/manage/branding/page.tsx

'use client';

import { useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useUser } from '@/entities/user';
import { Sparkles } from 'lucide-react';
import { BrandingSettingsForm } from '@/widgets/layout';

export default function BrandingSettingsPage() {
  return (
    <Suspense>
      <BrandingSettingsPageContent />
    </Suspense>
  );
}

function BrandingSettingsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const userContext = useUser();

  // Check if this is first-time setup
  const isWelcome = searchParams.get('welcome') === 'true';

  // Check permissions
  useEffect(() => {
    if (!userContext?.user) {
      router.push('/login');
      return;
    }

    if (userContext.user.role !== 'super_admin') {
      router.push('/dashboard');
      return;
    }
  }, [userContext, router]);

  if (!userContext?.user) {
    return null;
  }

  const handleSaveSuccess = () => {
    // If this is first-time setup, redirect to dashboard after a brief delay
    if (isWelcome) {
      setTimeout(() => {
        router.push('/dashboard');
      }, 1500);
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 sm:px-6 overflow-x-hidden">
      {/* Welcome Banner for First-Time Setup */}
      {isWelcome && (
        <div className="mb-6 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-info rounded-lg p-6">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <Sparkles className="h-6 w-6 text-info" />
            </div>
            <div className="ml-3 flex-1">
              <h3 className="text-lg font-semibold text-info mb-1">
                Welcome! Let&apos;s customize your organization
              </h3>
              <p className="text-sm text-info mb-3">
                Take a moment to personalize your workspace with your organization&apos;s branding. You can always update these settings later.
              </p>
              <button
                type="button"
                onClick={() => router.push('/dashboard')}
                className="text-sm text-info hover:text-info font-medium underline"
              >
                Skip for now and go to dashboard →
              </button>
            </div>
          </div>
        </div>
      )}

      <BrandingSettingsForm
        showCustomDomain
        onSaveSuccess={handleSaveSuccess}
      />
    </div>
  );
}
