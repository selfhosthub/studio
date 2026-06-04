// ui/widgets/layout/Footer.tsx

'use client';

import Link from 'next/link';
import Image from 'next/image';
import { useBranding } from '@/entities/organization';
import { usePageVisibility } from '@/entities/page-visibility';
interface FooterProps {
  className?: string;
}

const Divider = () => (
  <span className="text-muted">|</span>
);

const Footer = ({ className = '' }: FooterProps) => {
  const { branding } = useBranding();
  const { visibility } = usePageVisibility();

  return (
    <>
      <hr className="border-primary my-4" />
      <footer className={`bg-card text-primary py-4 md:py-6 ${className}`}>
        <div className="container mx-auto px-4">
          {/* Mobile: Compact inline footer */}
          <div className="md:hidden">
            {/* Logo/company + copyright */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                {branding.logoUrl ? (
                  <Image
                    src={branding.logoUrl}
                    alt={branding.companyName || 'Logo'}
                    width={80}
                    height={28}
                    className="h-7 w-auto"
                  />
                ) : branding.companyName ? (
                  <span className="font-semibold text-sm">{branding.companyName}</span>
                ) : null}
              </div>
              <span className="text-muted text-xs">
                &copy; {new Date().getFullYear()}
              </span>
            </div>

            {/* Inline links with pipe dividers between sections */}
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-secondary">
              {/* Product section */}
              <Link href="/features" prefetch={false} className="hover:text-primary">Features</Link>

              {/* Divider before Resources */}
              {(visibility.docs || visibility.support) && <Divider />}

              {/* Resources section */}
              {visibility.docs && (
                <Link href="/docs" prefetch={false} className="hover:text-primary">Docs</Link>
              )}
              {visibility.support && (
                <Link href="/support" prefetch={false} className="hover:text-primary">Support</Link>
              )}

              {/* Divider before Company */}
              {(visibility.about || visibility.contact) && <Divider />}

              {/* Company section */}
              {visibility.about && (
                <Link href="/about" prefetch={false} className="hover:text-primary">About</Link>
              )}
              {visibility.contact && (
                <Link href="/contact" prefetch={false} className="hover:text-primary">Contact</Link>
              )}

              {/* Divider before Legal */}
              {(visibility.terms || visibility.privacy || visibility.compliance) && <Divider />}

              {/* Legal section */}
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
                {branding.logoUrl ? (
                  <Image
                    src={branding.logoUrl}
                    alt={branding.companyName || 'Logo'}
                    width={120}
                    height={40}
                    className="h-10 w-auto mb-4"
                  />
                ) : branding.companyName ? (
                  <h3 className="text-xl font-semibold mb-4">{branding.companyName}</h3>
                ) : null}
                {branding.tagline && (
                  <p className="text-secondary">
                    {branding.tagline}
                  </p>
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
              <p className="text-secondary">&copy; {new Date().getFullYear()}{branding.companyName ? ` ${branding.companyName}.` : ''} All rights reserved.</p>
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
};

export default Footer;