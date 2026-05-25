// ui/app/docs/providers/page.tsx

'use client';

import React, { Suspense, useEffect, useState, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Navbar, Footer, PageVisibilityGuard } from '@/widgets/layout';
import { ArrowLeft, Search, Lightbulb, AlertTriangle, Info, Link as LinkIcon } from 'lucide-react';
import { getProviderDocsList, getProviderDocContent, type ProviderDocInfo } from '@/shared/api';

export default function ProvidersDocsPage() {
  return (
    <Suspense fallback={
      <main className="flex min-h-screen flex-col bg-card">
        <Navbar />
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-pulse text-secondary">Loading provider documentation...</div>
        </div>
        <Footer />
      </main>
    }>
      <ProvidersDocsContent />
    </Suspense>
  );
}

function ProvidersDocsContent() {
  const searchParams = useSearchParams();
  const initialProvider = searchParams.get('provider');

  const [providers, setProviders] = useState<ProviderDocInfo[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(initialProvider);
  const [content, setContent] = useState<string | null>(null);
  const [docTitle, setDocTitle] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch provider list (mount-only)
  useEffect(() => {
    const fetchList = async () => {
      try {
        const data = await getProviderDocsList();
        const sorted = (data.providers || []).sort((a, b) =>
          a.title.localeCompare(b.title)
        );
        setProviders(sorted);
      } catch {
        setError('Failed to load provider documentation.');
      } finally {
        setIsLoadingList(false);
      }
    };
    fetchList();
  }, []);

  // Resolve the selected slug once providers are loaded - prefer the URL's
  // requested slug if it's valid, otherwise fall back to the first entry.
  useEffect(() => {
    if (providers.length === 0) return;
    if (!selectedSlug || !providers.some(p => p.id === selectedSlug)) {
      setSelectedSlug(providers[0].id);
    }
  }, [providers, selectedSlug]);

  // Fetch content when selection changes
  useEffect(() => {
    if (!selectedSlug) return;

    const fetchContent = async () => {
      setIsLoadingContent(true);
      try {
        const data = await getProviderDocContent(selectedSlug);
        setDocTitle(data.title);
        setContent(data.content);
      } catch {
        setContent(null);
        setDocTitle('');
      } finally {
        setIsLoadingContent(false);
      }
    };
    fetchContent();
  }, [selectedSlug]);

  // Filter providers by search
  const filteredProviders = useMemo(() => {
    if (!searchQuery.trim()) return providers;
    const q = searchQuery.toLowerCase();
    return providers.filter(
      p => p.title.toLowerCase().includes(q) || p.description.toLowerCase().includes(q)
    );
  }, [providers, searchQuery]);

  const handleSelect = useCallback((slug: string) => {
    setSelectedSlug(slug);
    // Scroll content area to top
    const contentArea = document.getElementById('provider-doc-content');
    contentArea?.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  if (isLoadingList) {
    return (
      <main className="flex min-h-screen flex-col bg-card">
        <Navbar />
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-pulse text-secondary">Loading provider documentation...</div>
        </div>
        <Footer />
      </main>
    );
  }

  if (error || providers.length === 0) {
    return (
      <main className="flex min-h-screen flex-col bg-card">
        <Navbar />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-primary mb-2">
              {error || 'No Provider Documentation Available'}
            </h1>
            <Link href="/docs" className="text-info hover:underline">
              Back to Documentation
            </Link>
          </div>
        </div>
        <Footer />
      </main>
    );
  }

  return (
    <PageVisibilityGuard page="docs">
      <div className="min-h-screen bg-card">
        <Navbar />

        <div className="flex h-[calc(100vh-4rem)]">
          {/* Left sidebar - provider index */}
          <aside className="w-72 flex-shrink-0 border-r border-primary flex flex-col bg-card">
            {/* Back link */}
            <div className="px-4 pt-4 pb-2">
              <Link
                href="/docs"
                className="inline-flex items-center text-sm text-secondary hover:text-info"
              >
                <ArrowLeft className="w-4 h-4 mr-1" />
                All Docs
              </Link>
            </div>

            <div className="px-4 pb-2">
              <h2 className="text-sm font-semibold text-primary">Providers</h2>
            </div>

            {/* Search field */}
            <div className="px-4 pb-3">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter providers..."
                  className="w-full pl-8 pr-3 py-1.5 text-sm border border-primary rounded bg-surface text-primary placeholder:text-muted focus:outline-none focus:border-info"
                />
              </div>
            </div>

            {/* Provider list */}
            <nav className="flex-1 overflow-y-auto px-2 pb-4">
              {filteredProviders.length === 0 ? (
                <p className="px-2 py-4 text-sm text-muted">No providers match your search.</p>
              ) : (
                <div className="space-y-0.5">
                  {filteredProviders.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => handleSelect(p.id)}
                      className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
                        selectedSlug === p.id
                          ? 'bg-info-subtle text-info font-medium'
                          : 'text-secondary hover:bg-surface hover:text-primary'
                      }`}
                    >
                      {p.title.replace(/ Provider$/, '')}
                    </button>
                  ))}
                </div>
              )}
            </nav>
          </aside>

          {/* Right content - selected provider doc */}
          <div id="provider-doc-content" className="flex-1 overflow-y-auto">
            {isLoadingContent && (
              <div className="flex items-center justify-center py-20">
                <div className="animate-pulse text-secondary">Loading...</div>
              </div>
            )}

            {!isLoadingContent && !content && (
              <div className="flex items-center justify-center py-20">
                <p className="text-secondary">Select a provider to view documentation.</p>
              </div>
            )}

            {!isLoadingContent && content && (
              <article className="max-w-4xl mx-auto px-8 py-8">
                <div className="prose prose-gray dark:prose-invert max-w-none
                  prose-headings:scroll-mt-20
                  prose-h1:text-3xl prose-h1:font-bold prose-h1:mb-8
                  prose-h2:text-2xl prose-h2:font-semibold prose-h2:mt-12 prose-h2:mb-4 prose-h2:pb-2 prose-h2:border-b prose-h2:border-gray-200 dark:prose-h2:border-gray-700 prose-h2:border-l-4 prose-h2:border-l-blue-500 prose-h2:pl-4 prose-h2:-ml-4
                  prose-h3:text-xl prose-h3:font-medium prose-h3:mt-8 prose-h3:mb-3
                  prose-p:text-gray-700 dark:prose-p:text-gray-300 prose-p:leading-relaxed
                  prose-a:text-blue-600 dark:prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline
                  prose-code:text-pink-600 dark:prose-code:text-pink-400 prose-code:bg-gray-100 dark:prose-code:bg-gray-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
                  prose-pre:bg-gray-900 dark:prose-pre:bg-gray-950 prose-pre:text-gray-100 prose-pre:overflow-x-auto
                  prose-table:w-full prose-table:text-sm
                  prose-th:bg-gray-100 dark:prose-th:bg-gray-800 prose-th:px-4 prose-th:py-2 prose-th:text-left prose-th:font-medium
                  prose-td:px-4 prose-td:py-2 prose-td:border-t prose-td:border-gray-200 dark:prose-td:border-gray-700
                  prose-ul:list-disc prose-ul:pl-6
                  prose-ol:list-decimal prose-ol:pl-6
                  prose-li:my-1
                  prose-hr:border-gray-200 dark:prose-hr:border-gray-700 prose-hr:my-8
                  prose-blockquote:border-l-4 prose-blockquote:border-blue-500 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-gray-600 dark:prose-blockquote:text-gray-400
                ">
                  {/* css-check-ignore: prose typography classes require raw color values */}
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h2: ({ children, ...props }) => {
                        const text = String(children);
                        const id = text
                          .toLowerCase()
                          .replace(/[^\w\s-]/g, '')
                          .replace(/\s+/g, '-')
                          .replace(/--+/g, '-');
                        return (
                          <h2 id={id} className="group" {...props}>
                            {children}
                            <a
                              href={`#${id}`}
                              className="ml-2 opacity-0 group-hover:opacity-100 transition-opacity text-muted hover:text-info"
                              aria-label="Link to this section"
                            >
                              <LinkIcon className="inline w-4 h-4" />
                            </a>
                          </h2>
                        );
                      },
                      h3: ({ children, ...props }) => {
                        const text = String(children);
                        const id = text
                          .toLowerCase()
                          .replace(/[^\w\s-]/g, '')
                          .replace(/\s+/g, '-')
                          .replace(/--+/g, '-');
                        return (
                          <h3 id={id} className="group" {...props}>
                            {children}
                            <a
                              href={`#${id}`}
                              className="ml-2 opacity-0 group-hover:opacity-100 transition-opacity text-muted hover:text-info"
                              aria-label="Link to this section"
                            >
                              <LinkIcon className="inline w-4 h-4" />
                            </a>
                          </h3>
                        );
                      },
                      p: ({ children, ...props }) => {
                        const text = String(children);
                        if (text.startsWith('**Tip:**') || text.startsWith('Tip:')) {
                          const c = text.replace(/^\*\*Tip:\*\*\s*|^Tip:\s*/, '');
                          return (
                            <div className="not-prose my-4 flex gap-3 rounded-lg border border-info bg-info-subtle p-4">
                              <Lightbulb className="w-5 h-5 text-info flex-shrink-0 mt-0.5" />
                              <div className="text-sm text-info">{c}</div>
                            </div>
                          );
                        }
                        if (text.startsWith('**Warning:**') || text.startsWith('Warning:')) {
                          const c = text.replace(/^\*\*Warning:\*\*\s*|^Warning:\s*/, '');
                          return (
                            <div className="not-prose my-4 flex gap-3 rounded-lg border border-warning bg-warning-subtle p-4">
                              <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
                              <div className="text-sm text-warning">{c}</div>
                            </div>
                          );
                        }
                        if (text.startsWith('**Note:**') || text.startsWith('Note:')) {
                          const c = text.replace(/^\*\*Note:\*\*\s*|^Note:\s*/, '');
                          return (
                            <div className="not-prose my-4 flex gap-3 rounded-lg border border-primary bg-surface p-4">
                              <Info className="w-5 h-5 text-secondary flex-shrink-0 mt-0.5" />
                              <div className="text-sm text-secondary">{c}</div>
                            </div>
                          );
                        }
                        return <p {...props}>{children}</p>;
                      },
                    }}
                  >
                    {content}
                  </ReactMarkdown>
                </div>
              </article>
            )}
          </div>
        </div>
      </div>
    </PageVisibilityGuard>
  );
}
