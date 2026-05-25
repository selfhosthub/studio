// ui/widgets/layout/Navbar.tsx

'use client';

import Link from 'next/link';
import Image from 'next/image';
import { useState, useEffect } from 'react';
import { useUser } from '@/entities/user';
import { useBranding } from '@/entities/organization';
import { Menu, HelpCircle } from 'lucide-react';
import DarkModeToggle from "./DarkModeToggle";
import { NotificationBell } from '@/features/notifications';
import { useRegistrationSettings } from '@/entities/registration';

type NavbarProps = {
  onMobileMenuToggle?: () => void;
};

const Navbar = ({ onMobileMenuToggle }: NavbarProps) => {
  // Access user context directly
  const userContext = useUser();

  // Get branding configuration
  const { branding } = useBranding();
  const { allowRegistration } = useRegistrationSettings();

  // Use user data directly from context, with loading state
  const userData = userContext?.user || null;
  const userLogout = userContext?.logout || (() => {});
  const isAuthLoading = userContext?.isLoading ?? true;

  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  const toggleMenu = () => setIsMenuOpen(!isMenuOpen);

  // Handle scroll effect
  useEffect(() => {
    const handleScroll = () => {
      if (window.scrollY > 10) {
        setScrolled(true);
      } else {
        setScrolled(false);
      }
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <nav
      className={`transition-all duration-300 bg-card text-primary ${
        scrolled ? 'shadow-md' : 'shadow-sm'
      }`}
    >
      <div className="px-4 lg:container mx-auto">
        <div className="flex h-12 items-center justify-between">
          {/* Mobile menu button */}
          <div className="flex md:hidden">
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-md p-1.5 opacity-80 hover:opacity-100 transition-opacity text-info"
              onClick={onMobileMenuToggle}
              aria-label="Toggle mobile menu"
              data-testid="mobile-menu-button"
            >
              <Menu size={18} />
            </button>
          </div>

          {/* Logo */}
          <div className="flex items-center">
            <Link href="/" className="flex items-center">
              {branding.logoUrl ? (
                <Image
                  src={branding.logoUrl}
                  alt={branding.companyName || 'Logo'}
                  width={120}
                  height={40}
                  className="h-8 md:h-10 w-auto"
                  priority
                />
              ) : branding.shortName ? (
                <span className="text-xl font-bold md:text-2xl text-info">
                  {branding.shortName}
                </span>
              ) : null}
            </Link>
          </div>

          {/* Right side buttons */}
          <div className="flex items-center space-x-2 md:space-x-4">
            {isAuthLoading ? (
              // Show nothing while loading to prevent flash
              <div className="w-8 h-8" />
            ) : userData ? (
              <>
                {/* Dark Mode Toggle - only for logged in users */}
                <DarkModeToggle />

                {/* Notification bell */}
                <NotificationBell />

                {/* Help icon - links to documentation */}
                <Link
                  href={userData.role === 'super_admin' ? '/docs/super-admin' : '/docs'}
                  className="p-1.5 rounded-md opacity-80 hover:opacity-100 transition-opacity text-info"
                  title="Documentation"
                >
                  <HelpCircle size={20} />
                </Link>

                {/* Dashboard link (hidden on mobile) */}
                <Link
                  href="/dashboard"
                  className="hidden md:block font-medium opacity-90 hover:opacity-100 transition-opacity text-info"
                >
                  Dashboard
                </Link>

                {/* User profile dropdown */}
                <div className="relative">
                  <button
                    onClick={toggleMenu}
                    className="flex items-center text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded opacity-90 hover:opacity-100 transition-opacity text-info"
                    aria-expanded={isMenuOpen}
                    aria-haspopup="true"
                  >
                    <span
                      className="h-8 w-8 rounded-full flex items-center justify-center text-sm font-medium uppercase"
                      style={{
                        backgroundColor: branding.primaryColor,
                        color: 'white'
                      }}
                    >
                      {userData?.username?.charAt(0) || 'U'}
                    </span>
                    <span className="ml-2 hidden md:inline">{userData?.username || 'User'}</span>
                    <svg className="ml-1 h-4 w-4 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {isMenuOpen && (
                    <div className="absolute right-0 mt-2 w-48 rounded-md shadow-lg py-1 bg-card ring-1 ring-black ring-opacity-5 z-10">
                      <div className="px-4 py-3">
                        <p className="text-sm">Signed in as</p>
                        <p className="text-sm font-medium text-primary truncate">{userData.email}</p>
                      </div>
                      <div className="border-t border-secondary"></div>
                      <Link href="/profile" className="block px-4 py-2 text-sm text-secondary hover:bg-card">
                        Your Profile
                      </Link>
                      <Link href="/settings" className="block px-4 py-2 text-sm text-secondary hover:bg-card">
                        Settings
                      </Link>
                      <div className="border-t border-secondary"></div>
                      <button
                        onClick={userLogout}
                        className="block w-full text-left px-4 py-2 text-sm text-secondary hover:bg-card"
                      >
                        Sign out
                      </button>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <>
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
                      backgroundColor: branding.primaryColor,
                      color: 'white'
                    }}
                  >
                    Sign Up
                  </Link>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;