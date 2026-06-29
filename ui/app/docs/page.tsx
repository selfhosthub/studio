// ui/app/docs/page.tsx

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Navbar, Footer, PageVisibilityGuard } from '@/widgets/layout';
import { Book, Settings, Server, Box, ArrowRight } from 'lucide-react';
import { useUser } from '@/entities/user';
import { getPublicDocsCatalog, getProviderDocsList, apiRequest, type DocsManifest, type ProviderDocInfo } from '@/shared/api';

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  'book-open': Book,
  'settings': Settings,
  'server': Server,
};

export default function DocsPage() {
  const { user, status } = useUser();
  const [manifest, setManifest] = useState<DocsManifest | null>(null);
  const [fullManifest, setFullManifest] = useState<DocsManifest | null>(null);
  const [providerDocs, setProviderDocs] = useState<ProviderDocInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';

  useEffect(() => {
    const fetchManifest = async () => {
      try {
        // If admin+, fetch role-filtered manifest; otherwise fetch public manifest
        if (isAdmin && status === 'authenticated') {
          try {
            const fullData = await apiRequest<DocsManifest>('/docs/catalog/full');
            setFullManifest(fullData);
            // Fetch provider docs list for admin too
            try {
              const providerData = await getProviderDocsList();
              setProviderDocs(providerData.providers || []);
            } catch {
              // Provider docs are optional; ignore errors
            }
            setIsLoading(false);
            return;
          } catch {
            // Fall through to public manifest
          }
        }

        // Fallback: fetch public manifest
        const data = await getPublicDocsCatalog();
        setManifest(data);

        // Fetch provider docs list
        try {
          const providerData = await getProviderDocsList();
          setProviderDocs(providerData.providers || []);
        } catch {
          // Provider docs are optional; ignore errors
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load documentation');
      } finally {
        setIsLoading(false);
      }
    };

    // Wait for auth status to be known before fetching
    if (status !== 'loading') {
      fetchManifest();
    }
  }, [isAdmin, status]);

  // Use full manifest if admin+, otherwise use public manifest
  const displayManifest = isAdmin && fullManifest ? fullManifest : manifest;

  return (
    <PageVisibilityGuard page="docs">
      {(isLoading || status === 'loading') ? (
        <main className="flex min-h-screen flex-col bg-card">
          <Navbar />
          <div className="flex-1 flex items-center justify-center">
            <div className="animate-pulse text-secondary">Loading documentation...</div>
          </div>
          <Footer />
        </main>
      ) : (error || !displayManifest) ? (
        <main className="flex min-h-screen flex-col bg-card">
          <Navbar />
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Book className="w-16 h-16 text-muted mx-auto mb-4" />
              <h1 className="text-2xl font-bold text-primary mb-2">
                Documentation Not Available
              </h1>
              <p className="text-secondary">
                {error || 'Please contact your administrator.'}
              </p>
            </div>
          </div>
          <Footer />
        </main>
      ) : (
      <main className="flex min-h-screen flex-col bg-card">
        <Navbar />

        {/* Hero Section */}
        <section className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white py-16"> {/* css-check-ignore: no semantic token */}
          <div className="container mx-auto px-4">
            <div className="max-w-4xl mx-auto text-center">
              <h1 className="text-4xl font-bold mb-4">Documentation</h1>
              <p className="text-xl text-blue-100"> {/* css-check-ignore: gradient header */}
                Learn how to use the platform effectively
              </p>
              <div className="mt-4 inline-flex items-center px-3 py-1 rounded-full bg-card/20 text-sm">
                v{displayManifest.version}
              </div>
            </div>
          </div>
        </section>

        {/* Documentation Cards */}
        <section className="py-16">
          <div className="container mx-auto px-4">
            <div className="max-w-4xl mx-auto">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {displayManifest.docs.map((doc) => {
                  const Icon = iconMap[doc.icon] || Book;
                  const href = doc.id === 'super-admin'
                    ? '/docs/super-admin'
                    : `/docs/${doc.id}`;

                  return (
                    <Link
                      key={doc.id}
                      href={href}
                      className="group bg-card p-6 rounded-xl shadow-sm hover:shadow-lg transition-all border border-primary hover:border-info"
                    >
                      <div className="flex items-start gap-4">
                        <div className="w-12 h-12 bg-info-subtle rounded-lg flex items-center justify-center flex-shrink-0">
                          <Icon className="w-6 h-6 text-info" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="text-lg font-semibold text-primary group-hover:text-info transition-colors">
                              {doc.title}
                            </h3>
                            {!doc.public && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300"> {/* css-check-ignore: purple brand badge */}
                                {doc.id === 'super-admin' ? 'Super Admin' : 'Admin'}
                              </span>
                            )}
                          </div>
                          <p className="text-secondary text-sm">
                            {doc.description}
                          </p>
                        </div>
                        <ArrowRight className="w-5 h-5 text-muted group-hover:text-info transition-colors flex-shrink-0" />
                      </div>
                    </Link>
                  );
                })}
              </div>
            </div>
          </div>
        </section>

        {/* Provider Documentation Card */}
        {providerDocs.length > 0 && (
          <section className="py-16 bg-surface">
            <div className="container mx-auto px-4">
              <div className="max-w-4xl mx-auto">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <Link
                    href="/docs/providers"
                    className="group bg-card p-6 rounded-xl shadow-sm hover:shadow-lg transition-all border border-primary hover:border-info"
                  >
                    <div className="flex items-start gap-4">
                      <div className="w-12 h-12 bg-info-subtle rounded-lg flex items-center justify-center flex-shrink-0">
                        <Box className="w-6 h-6 text-info" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-lg font-semibold text-primary group-hover:text-info transition-colors">
                          Provider Documentation
                        </h3>
                        <p className="text-secondary text-sm">
                          Setup guides, credentials, and service reference for {providerDocs.length} providers
                        </p>
                      </div>
                      <ArrowRight className="w-5 h-5 text-muted group-hover:text-info transition-colors flex-shrink-0" />
                    </div>
                  </Link>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Help Section */}
        <section className="py-12 bg-surface">
          <div className="container mx-auto px-4">
            <div className="max-w-4xl mx-auto text-center">
              <h2 className="text-2xl font-bold text-primary mb-4">
                Need Help?
              </h2>
              <p className="text-secondary mb-6">
                Can&apos;t find what you&apos;re looking for? Our support team is here to help.
              </p>
              <Link
                href="/support"
                className="btn-primary inline-flex items-center px-6 py-3"
              >
                Contact Support
                <ArrowRight className="w-4 h-4 ml-2" />
              </Link>
            </div>
          </div>
        </section>

        <Footer />
      </main>
      )}
    </PageVisibilityGuard>
  );
}
