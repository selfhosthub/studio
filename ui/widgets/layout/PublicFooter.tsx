// ui/widgets/layout/PublicFooter.tsx

import Link from 'next/link';
import Image from 'next/image';
import { serverFetch, getPageVisibility } from '@/shared/lib/page-visibility';
import { API_VERSION } from '@/shared/lib/config';

async function getBranding() {
  const response = await serverFetch(`${API_VERSION}/public/branding`, {
    next: { revalidate: 60 },
  } as RequestInit);

  if (response) {
    return response.json();
  }
  return null;
}

const Divider = () => (
  <span className="text-muted">|</span>
);

export default async function PublicFooter() {
  const [brandingData, visibility] = await Promise.all([
    getBranding(),
    getPageVisibility(),
  ]);

  const companyName = brandingData?.org_name || brandingData?.company_name || '';
  const shortName = brandingData?.short_name || '';
  const logoUrl = brandingData?.logo_url || null;
  const tagline = brandingData?.tagline || '';

  return (
    <>
      <hr className="border-primary my-4" />
      <footer className="bg-card text-primary py-4 md:py-6">
        <div className="container mx-auto px-4">
          {/* Mobile: Compact inline footer */}
          <div className="md:hidden">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                {logoUrl ? (
                  <Image
                    src={logoUrl}
                    alt={companyName || 'Logo'}
                    width={80}
                    height={28}
                    className="h-7 w-auto"
                  />
                ) : companyName ? (
                  <span className="font-semibold text-sm">{companyName}</span>
                ) : null}
              </div>
              <span className="text-muted text-xs">
                &copy; {new Date().getFullYear()}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-secondary">
              <Link href="/features" prefetch={false} className="hover:text-primary">Features</Link>

              {(visibility.docs || visibility.support) && <Divider />}

              {visibility.docs && (
                <Link href="/docs" prefetch={false} className="hover:text-primary">Docs</Link>
              )}
              {visibility.support && (
                <Link href="/support" prefetch={false} className="hover:text-primary">Support</Link>
              )}

              {(visibility.about || visibility.contact) && <Divider />}

              {visibility.about && (
                <Link href="/about" prefetch={false} className="hover:text-primary">About</Link>
              )}
              {visibility.contact && (
                <Link href="/contact" prefetch={false} className="hover:text-primary">Contact</Link>
              )}

              {(visibility.terms || visibility.privacy || visibility.compliance) && <Divider />}

              {visibility.terms && (
                <Link href="/terms" prefetch={false} className="hover:text-primary">Terms</Link>
              )}
              {visibility.privacy && (
                <Link href="/privacy" prefetch={false} className="hover:text-primary">Privacy</Link>
              )}
              {visibility.compliance && (
                <Link href="/compliance" prefetch={false} className="hover:text-primary">Compliance</Link>
              )}
            </div>
          </div>

          {/* Desktop: Full 4-column layout */}
          <div className="hidden md:block">
            <div className="grid grid-cols-4 gap-8">
              <div>
                {logoUrl ? (
                  <Image
                    src={logoUrl}
                    alt={companyName || 'Logo'}
                    width={120}
                    height={40}
                    className="h-10 w-auto mb-4"
                  />
                ) : companyName ? (
                  <h3 className="text-xl font-semibold mb-4">{companyName}</h3>
                ) : null}
                {tagline && (
                  <p className="text-secondary">{tagline}</p>
                )}
              </div>

              <div>
                <h4 className="font-semibold mb-4">Product</h4>
                <ul className="space-y-2">
                  <li><Link href="/features" prefetch={false} className="text-secondary hover:text-primary transition-colors">Features</Link></li>
                </ul>
              </div>

              <div>
                <h4 className="font-semibold mb-4">Resources</h4>
                <ul className="space-y-2">
                  {visibility.docs && (
                    <li><Link href="/docs" prefetch={false} className="text-secondary hover:text-primary transition-colors">Documentation</Link></li>
                  )}
                  {visibility.support && (
                    <li><Link href="/support" prefetch={false} className="text-secondary hover:text-primary transition-colors">Support</Link></li>
                  )}
                </ul>
              </div>

              <div>
                <h4 className="font-semibold mb-4">Company</h4>
                <ul className="space-y-2">
                  {visibility.about && (
                    <li><Link href="/about" prefetch={false} className="text-secondary hover:text-primary transition-colors">About Us</Link></li>
                  )}
                  {visibility.contact && (
                    <li><Link href="/contact" prefetch={false} className="text-secondary hover:text-primary transition-colors">Contact</Link></li>
                  )}
                </ul>
              </div>
            </div>

            <div className="border-t border-primary mt-8 pt-8 flex justify-between items-center">
              <p className="text-secondary">&copy; {new Date().getFullYear()}{companyName ? ` ${companyName}.` : ''} All rights reserved.</p>
              <div className="flex space-x-4">
                {visibility.terms && (
                  <Link href="/terms" prefetch={false} className="text-secondary hover:text-primary transition-colors">Terms</Link>
                )}
                {visibility.privacy && (
                  <Link href="/privacy" prefetch={false} className="text-secondary hover:text-primary transition-colors">Privacy</Link>
                )}
                {visibility.compliance && (
                  <Link href="/compliance" prefetch={false} className="text-secondary hover:text-primary transition-colors">Compliance</Link>
                )}
              </div>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
}
