// ui/app/organizations/[id]/branding/page.tsx

'use client';

import { useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useUser } from '@/entities/user';
import { BrandingSettingsForm } from '@/widgets/layout';

export default function OrganizationBrandingPage() {
  const router = useRouter();
  const params = useParams();
  const userContext = useUser();
  const orgId = params.id as string;

  // Check permissions
  const isSuperAdmin = userContext?.user?.role === 'super_admin';
  const isViewingOtherOrg = isSuperAdmin && userContext?.user?.org_id !== orgId;
  const canView = isSuperAdmin || userContext?.user?.org_id === orgId;
  // Super-admin viewing another org's branding is read-only
  const readOnly = isViewingOtherOrg;

  useEffect(() => {
    if (!userContext?.user) {
      router.push('/login');
      return;
    }

    if (!canView) {
      router.push('/dashboard');
      return;
    }
  }, [userContext, canView, router]);

  if (!userContext?.user) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted">Loading...</div>
      </div>
    );
  }

  if (!canView) {
    return null;
  }

  return (
    <div className="max-w-4xl mx-auto">
      <BrandingSettingsForm orgId={orgId} readOnly={readOnly} />
    </div>
  );
}
