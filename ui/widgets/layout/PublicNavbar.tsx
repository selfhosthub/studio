// ui/widgets/layout/PublicNavbar.tsx

import Link from 'next/link';
import Image from 'next/image';
import { serverFetch } from '@/shared/lib/page-visibility';
import { API_VERSION } from '@/shared/lib/config';
import DarkModeToggle from './DarkModeToggle';

const defaultPrimaryColor = '#3B82F6';

async function getBranding() {
  const response = await serverFetch(`${API_VERSION}/public/branding`, {
    next: { revalidate: 60 },
  } as RequestInit);

  if (response) {
    return response.json();
  }
  return null;
}

async function getRegistrationSettings() {
  const response = await serverFetch(`${API_VERSION}/public/registration-settings`, {
    next: { revalidate: 60 },
  } as RequestInit);

  if (response) {
    const data = await response.json();
    return data.allow_registration ?? true;
  }
  return false;
}

export default async function PublicNavbar() {
  const [brandingData, allowRegistration] = await Promise.all([
    getBranding(),
    getRegistrationSettings(),
  ]);

  const shortName = brandingData?.short_name || '';
  const logoUrl = brandingData?.logo_url || null;
  const companyName = brandingData?.org_name || brandingData?.company_name || '';
  const primaryColor = brandingData?.primary_color || defaultPrimaryColor;

  return (
    <nav className="sticky top-0 z-10 shadow-sm bg-card text-primary">
      <div className="px-4 lg:container mx-auto">
        <div className="flex h-12 items-center justify-between">
          {/* Logo */}
          <div className="flex items-center">
            <Link href="/" className="flex items-center">
              {logoUrl ? (
                <Image
                  src={logoUrl}
                  alt={companyName || 'Logo'}
                  width={120}
                  height={40}
                  className="h-8 md:h-10 w-auto"
                  priority
                />
              ) : shortName ? (
                <span className="text-xl font-bold md:text-2xl text-info">
                  {shortName}
                </span>
              ) : null}
            </Link>
          </div>

          {/* Right side */}
          <div className="flex items-center space-x-2 md:space-x-4">
            <DarkModeToggle />
            <Link
              href="/login"
              className="font-medium opacity-90 hover:opacity-100 transition-opacity text-info"
            >
              Login
            </Link>
            {allowRegistration && (
              <Link
                href="/register"
                className="px-4 py-2 rounded-md font-medium transition-opacity hover:opacity-90"
                style={{
                  backgroundColor: primaryColor,
                  color: 'white',
                }}
              >
                Sign Up
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
