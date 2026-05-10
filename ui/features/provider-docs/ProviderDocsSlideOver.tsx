// ui/features/provider-docs/ProviderDocsSlideOver.tsx

'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { X, ExternalLink, Lightbulb, AlertTriangle, Info } from 'lucide-react';
import { getProviderDocContent } from '@/shared/api';

interface AlternateProvider {
  slug: string;
  name: string;
}

interface ProviderDocsSlideOverProps {
  slug: string;
  isOpen: boolean;
  onClose: () => void;
  /** Other providers for the same service type - shown at the bottom as "See also" links */
  alternateProviders?: AlternateProvider[];
  /** Override the default fetch function (defaults to getProviderDocContent) */
  fetchContent?: (slug: string) => Promise<{ id: string; title: string; content: string }>;
}

const PANEL_WIDTH = 480;

export function ProviderDocsSlideOver({ slug, isOpen, onClose, alternateProviders, fetchContent }: ProviderDocsSlideOverProps) {
  const [activeSlug, setActiveSlug] = useState(slug);
  const [content, setContent] = useState<string | null>(null);
  const [title, setTitle] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isMounted, setIsMounted] = useState(false);

  // Sync activeSlug when parent slug changes
  useEffect(() => {
    setActiveSlug(slug);
  }, [slug]);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Fetch doc content when slug changes or panel opens
  useEffect(() => {
    if (!isOpen || !activeSlug) return;

    const fetchDoc = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await (fetchContent ?? getProviderDocContent)(activeSlug);
        setTitle(data.title);
        setContent(data.content);
      } catch {
        setError('Documentation not available for this provider.');
        setContent(null);
      } finally {
        setIsLoading(false);
      }
    };

    fetchDoc();
  }, [activeSlug, isOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Generate simple TOC from headings
  const headings = useMemo(() => {
    if (!content) return [];
    const regex = /^(#{2})\s+(.+)$/gm;
    const items: { id: string; text: string }[] = [];
    let match;
    while ((match = regex.exec(content)) !== null) {
      const text = match[2].trim();
      const id = text
        .toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/--+/g, '-');
      items.push({ id, text });
    }
    return items;
  }, [content]);

  if (!isMounted) return null;

  const panel = (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-[60] bg-black/20 backdrop-blur-[1px]"
          onClick={onClose}
          data-provider-docs-backdrop
        />
      )}

      {/* Panel */}
      <div
        className={`fixed top-0 right-0 z-[61] h-screen bg-surface border-l border-info shadow-xl transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}
        style={{ width: PANEL_WIDTH }}
        data-provider-docs-panel
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-primary">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-primary truncate">
              {title || 'Provider Documentation'}
            </h3>
          </div>
          <div className="flex items-center gap-2 ml-2">
            <a
              href={`/docs/providers/${activeSlug}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted hover:text-info transition-colors"
              title="Open in new tab"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
            <button
              onClick={onClose}
              className="text-muted hover:text-secondary transition-colors"
              aria-label="Close documentation"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Quick nav */}
        {headings.length > 0 && (
          <div className="px-4 py-2 border-b border-primary overflow-x-auto">
            <div className="flex gap-2 flex-nowrap">
              {headings.map((h) => (
                <a
                  key={h.id}
                  href={`#docs-panel-${h.id}`}
                  className="text-xs px-2 py-1 rounded bg-surface text-secondary hover:text-info whitespace-nowrap"
                  onClick={(e) => {
                    e.preventDefault();
                    const el = document.getElementById(`docs-panel-${h.id}`);
                    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                  }}
                >
                  {h.text}
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Content */}
        <div className="overflow-y-auto h-[calc(100vh-7rem)] px-4 py-4">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-pulse text-secondary text-sm">Loading documentation...</div>
            </div>
          )}

          {error && (
            <div className="text-center py-12">
              <p className="text-secondary text-sm">{error}</p>
            </div>
          )}

          {!isLoading && !error && content && (
            <div className="prose prose-sm prose-gray dark:prose-invert max-w-none
              prose-headings:scroll-mt-4
              prose-h1:text-xl prose-h1:font-bold prose-h1:mb-4
              prose-h2:text-lg prose-h2:font-semibold prose-h2:mt-8 prose-h2:mb-3 prose-h2:pb-1 prose-h2:border-b prose-h2:border-gray-200 dark:prose-h2:border-gray-700 // css-check-ignore
              prose-h3:text-base prose-h3:font-medium prose-h3:mt-6 prose-h3:mb-2
              prose-p:text-gray-700 dark:prose-p:text-gray-300 prose-p:leading-relaxed // css-check-ignore
              prose-a:text-blue-600 dark:prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline // css-check-ignore
              prose-code:text-pink-600 dark:prose-code:text-pink-400 prose-code:bg-gray-100 dark:prose-code:bg-gray-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none // css-check-ignore
              prose-pre:bg-gray-900 dark:prose-pre:bg-gray-950 prose-pre:text-gray-100 prose-pre:overflow-x-auto prose-pre:text-xs // css-check-ignore
              prose-table:w-full prose-table:text-xs
              prose-th:bg-gray-100 dark:prose-th:bg-gray-800 prose-th:px-3 prose-th:py-1.5 prose-th:text-left prose-th:font-medium // css-check-ignore
              prose-td:px-3 prose-td:py-1.5 prose-td:border-t prose-td:border-gray-200 dark:prose-td:border-gray-700 // css-check-ignore
              prose-ul:list-disc prose-ul:pl-5
              prose-ol:list-decimal prose-ol:pl-5
              prose-li:my-0.5
              prose-hr:border-gray-200 dark:prose-hr:border-gray-700 prose-hr:my-6 // css-check-ignore
              prose-blockquote:border-l-4 prose-blockquote:border-blue-500 prose-blockquote:pl-3 prose-blockquote:italic prose-blockquote:text-gray-600 dark:prose-blockquote:text-gray-400 // css-check-ignore
            ">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h2: ({ children, ...props }) => {
                    const text = String(children);
                    const id = 'docs-panel-' + text
                      .toLowerCase()
                      .replace(/[^\w\s-]/g, '')
                      .replace(/\s+/g, '-')
                      .replace(/--+/g, '-');
                    return <h2 id={id} {...props}>{children}</h2>;
                  },
                  h3: ({ children, ...props }) => {
                    const text = String(children);
                    const id = 'docs-panel-' + text
                      .toLowerCase()
                      .replace(/[^\w\s-]/g, '')
                      .replace(/\s+/g, '-')
                      .replace(/--+/g, '-');
                    return <h3 id={id} {...props}>{children}</h3>;
                  },
                  p: ({ children, ...props }) => {
                    const text = String(children);
                    if (text.startsWith('**Tip:**') || text.startsWith('Tip:')) {
                      const c = text.replace(/^\*\*Tip:\*\*\s*|^Tip:\s*/, '');
                      return (
                        <div className="not-prose my-3 flex gap-2 rounded-lg border border-info bg-info-subtle p-3">
                          <Lightbulb className="w-4 h-4 text-info flex-shrink-0 mt-0.5" />
                          <div className="text-xs text-info">{c}</div>
                        </div>
                      );
                    }
                    if (text.startsWith('**Warning:**') || text.startsWith('Warning:')) {
                      const c = text.replace(/^\*\*Warning:\*\*\s*|^Warning:\s*/, '');
                      return (
                        <div className="not-prose my-3 flex gap-2 rounded-lg border border-warning bg-warning-subtle p-3">
                          <AlertTriangle className="w-4 h-4 text-warning flex-shrink-0 mt-0.5" />
                          <div className="text-xs text-warning">{c}</div>
                        </div>
                      );
                    }
                    if (text.startsWith('**Note:**') || text.startsWith('Note:')) {
                      const c = text.replace(/^\*\*Note:\*\*\s*|^Note:\s*/, '');
                      return (
                        <div className="not-prose my-3 flex gap-2 rounded-lg border border-primary bg-surface p-3">
                          <Info className="w-4 h-4 text-secondary flex-shrink-0 mt-0.5" />
                          <div className="text-xs text-secondary">{c}</div>
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
          )}

          {/* Alternate providers for this service type */}
          {!isLoading && alternateProviders && alternateProviders.length > 0 && (
            <div className="mt-8 pt-4 border-t border-primary">
              <h4 className="text-xs font-semibold text-secondary uppercase tracking-wider mb-2">
                See also
              </h4>
              <div className="flex flex-wrap gap-2">
                {alternateProviders.map((alt) => (
                  <button
                    key={alt.slug}
                    onClick={() => {
                      setActiveSlug(alt.slug);
                      // Scroll content to top
                      const container = document.querySelector('[data-provider-docs-panel] > div:last-child');
                      container?.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                      activeSlug === alt.slug
                        ? 'border-info bg-info-subtle text-info'
                        : 'border-primary bg-surface text-secondary hover:text-info hover:border-info'
                    }`}
                  >
                    {alt.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );

  return createPortal(panel, document.body);
}
