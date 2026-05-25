// ui/app/docs/[slug]/page.tsx

'use client';

import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useParams, notFound } from 'next/navigation';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Navbar, Footer, PageVisibilityGuard } from '@/widgets/layout';
import { ArrowLeft, Menu, X, ChevronRight, ChevronDown, Lightbulb, AlertTriangle, Info, Link as LinkIcon } from 'lucide-react';
import { useUser } from '@/entities/user';
import { apiRequest, publicApiRequest } from '@/shared/api';

interface DocContent {
  id: string;
  title: string;
  content: string;
}

interface TocItem {
  id: string;
  text: string;
  level: number;
}

interface TocSection {
  id: string;
  text: string;
  children: TocItem[];
}

function generateToc(content: string): TocItem[] {
  const headingRegex = /^(#{2,3})\s+(.+)$/gm;
  const toc: TocItem[] = [];
  let match;

  while ((match = headingRegex.exec(content)) !== null) {
    const level = match[1].length;
    const text = match[2].trim();
    const id = text
      .toLowerCase()
      .replace(/[^\w\s-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/--+/g, '-');

    toc.push({ id, text, level });
  }

  return toc;
}

// Group flat TOC items into sections (H2 with nested H3s)
function groupTocIntoSections(toc: TocItem[]): TocSection[] {
  const sections: TocSection[] = [];
  let currentSection: TocSection | null = null;

  for (const item of toc) {
    if (item.level === 2) {
      // Start a new section
      currentSection = { id: item.id, text: item.text, children: [] };
      sections.push(currentSection);
    } else if (item.level === 3 && currentSection) {
      // Add to current section's children
      currentSection.children.push(item);
    }
  }

  return sections;
}

export default function DocViewerPage() {
  const params = useParams();
  const slug = params.slug as string;

  const [doc, setDoc] = useState<DocContent | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  const { user } = useUser();

  // Validate slug - only allow 'user' and 'admin'
  const validSlugs = ['user', 'admin'];
  const isValidSlug = validSlugs.includes(slug);

  useEffect(() => {
    if (!isValidSlug) {
      return;
    }

    const fetchDoc = async () => {
      try {
        let data: DocContent;
        if (slug === 'admin') {
          // Admin docs require authentication
          data = await apiRequest<DocContent>('/docs/admin/content');
        } else {
          // Public docs
          data = await publicApiRequest<DocContent>(`/docs/${slug}`);
        }
        setDoc(data);
      } catch (err) {
        const status = (err as Error & { status?: number }).status;
        if (status === 404) {
          setError('Documentation not found');
        } else if (status === 403) {
          setError('You need to be logged in as an admin to view this guide');
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load documentation');
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchDoc();
  }, [slug, isValidSlug, user]);

  const toc = useMemo(() => {
    if (!doc?.content) return [];
    return generateToc(doc.content);
  }, [doc?.content]);

  const tocSections = useMemo(() => {
    return groupTocIntoSections(toc);
  }, [toc]);

  // Toggle section expansion (only one section open at a time)
  const toggleSection = useCallback((sectionId: string) => {
    setExpandedSections(prev => {
      if (prev.has(sectionId)) {
        // Close this section
        return new Set();
      } else {
        // Open this section, close others
        return new Set([sectionId]);
      }
    });
  }, []);

  // Set up IntersectionObserver to track which section is in view
  useEffect(() => {
    if (!doc?.content) return;

    // Wait for content to render
    const timer = setTimeout(() => {
      const headings = document.querySelectorAll('h2[id], h3[id]');

      observerRef.current = new IntersectionObserver(
        (entries) => {
          // Find the first heading that's intersecting
          for (const entry of entries) {
            if (entry.isIntersecting) {
              const id = entry.target.id;
              // Find which section this heading belongs to
              const section = tocSections.find(
                s => s.id === id || s.children.some(c => c.id === id)
              );
              if (section) {
                setActiveSection(section.id);
                // Auto-expand the active section (only one at a time)
                setExpandedSections(prev => {
                  if (prev.has(section.id)) return prev;
                  return new Set([section.id]);
                });
              }
              break;
            }
          }
        },
        { rootMargin: '-80px 0px -80% 0px', threshold: 0 }
      );

      headings.forEach(heading => observerRef.current?.observe(heading));
    }, 100);

    return () => {
      clearTimeout(timer);
      observerRef.current?.disconnect();
    };
  }, [doc?.content, tocSections]);

  if (!isValidSlug) {
    notFound();
  }

  if (isLoading) {
    return (
      <main className="flex min-h-screen flex-col bg-card">
        <Navbar />
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-pulse text-secondary">Loading documentation...</div>
        </div>
        <Footer />
      </main>
    );
  }

  if (error || !doc) {
    return (
      <main className="flex min-h-screen flex-col bg-card">
        <Navbar />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-primary mb-2">
              {error || 'Documentation Not Found'}
            </h1>
            <Link
              href="/docs"
              className="text-info hover:underline"
            >
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

        {/* Mobile TOC Toggle */}
        <div className="lg:hidden sticky top-0 z-20 bg-card border-b border-primary px-4 py-3">
          <button
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="flex items-center gap-2 text-secondary"
          >
            {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            <span>Table of Contents</span>
          </button>
        </div>

        {/* Fixed Sidebar - TOC */}
        <aside
          className={`
            ${isSidebarOpen ? 'block' : 'hidden'}
            lg:block
            fixed top-0 left-0 lg:top-16
            w-64 h-screen lg:h-[calc(100vh-4rem)]
            bg-card
            z-10
            p-4 lg:pl-8 lg:pr-4 lg:pt-6
            overflow-y-auto
            border-r border-primary lg:border-0
          `}
        >
          <div className="mb-4">
            <Link
              href="/docs"
              className="inline-flex items-center text-sm text-secondary hover:text-info"
            >
              <ArrowLeft className="w-4 h-4 mr-1" />
              All Docs
            </Link>
          </div>

          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              window.scrollTo({ top: 0, behavior: 'smooth' });
              setIsSidebarOpen(false);
            }}
            className="block text-sm font-semibold text-primary mb-4 hover:text-info transition-colors"
          >
            {doc.title}
          </a>

          <nav className="space-y-1 pb-8">
            {tocSections.map((section) => (
              <div key={section.id}>
                {/* Section header (H2) */}
                <div className="flex items-center">
                  {section.children.length > 0 && (
                    <button
                      onClick={() => toggleSection(section.id)}
                      className="p-0.5 -ml-1 mr-1 text-muted hover:text-secondary"
                      aria-label={expandedSections.has(section.id) ? 'Collapse section' : 'Expand section'}
                    >
                      {expandedSections.has(section.id) ? (
                        <ChevronDown className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5" />
                      )}
                    </button>
                  )}
                  <a
                    href={`#${section.id}`}
                    onClick={() => {
                      setIsSidebarOpen(false);
                      if (section.children.length > 0) {
                        // Open this section, close others
                        setExpandedSections(new Set([section.id]));
                      }
                    }}
                    className={`
                      flex-1 text-sm py-0.5
                      ${section.children.length === 0 ? 'pl-0' : ''}
                      ${activeSection === section.id
                        ? 'text-info font-medium'
                        : 'text-secondary'
                      }
                      hover:text-info
                      transition-colors
                    `}
                  >
                    {section.text}
                  </a>
                </div>

                {/* Children (H3s) - collapsible */}
                {section.children.length > 0 && expandedSections.has(section.id) && (
                  <div className="ml-4 mt-1 space-y-0.5">
                    {section.children.map((child) => (
                      <a
                        key={child.id}
                        href={`#${child.id}`}
                        onClick={() => setIsSidebarOpen(false)}
                        className="block text-sm py-0.5 text-secondary hover:text-info transition-colors"
                      >
                        {child.text}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </nav>
        </aside>

        {/* Main Content - offset for fixed sidebar */}
        <div className="lg:ml-64">
          <article className="max-w-4xl mx-auto px-4 lg:px-8 py-8">
            <div className="prose prose-gray dark:prose-invert max-w-none
              prose-headings:scroll-mt-20
              prose-h1:text-3xl prose-h1:font-bold prose-h1:mb-8
              prose-h2:text-2xl prose-h2:font-semibold prose-h2:mt-12 prose-h2:mb-4 prose-h2:pb-2 prose-h2:border-b prose-h2:border-gray-200 dark:prose-h2:border-gray-700 prose-h2:border-l-4 prose-h2:border-l-blue-500 prose-h2:pl-4 prose-h2:-ml-4 // css-check-ignore
              prose-h3:text-xl prose-h3:font-medium prose-h3:mt-8 prose-h3:mb-3
              prose-p:text-gray-700 dark:prose-p:text-gray-300 prose-p:leading-relaxed // css-check-ignore
              prose-a:text-blue-600 dark:prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline // css-check-ignore
              prose-code:text-pink-600 dark:prose-code:text-pink-400 prose-code:bg-gray-100 dark:prose-code:bg-gray-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none // css-check-ignore
              prose-pre:bg-gray-900 dark:prose-pre:bg-gray-950 prose-pre:text-gray-100 prose-pre:overflow-x-auto // css-check-ignore
              prose-table:w-full prose-table:text-sm
              prose-th:bg-gray-100 dark:prose-th:bg-gray-800 prose-th:px-4 prose-th:py-2 prose-th:text-left prose-th:font-medium // css-check-ignore
              prose-td:px-4 prose-td:py-2 prose-td:border-t prose-td:border-gray-200 dark:prose-td:border-gray-700 // css-check-ignore
              prose-ul:list-disc prose-ul:pl-6
              prose-ol:list-decimal prose-ol:pl-6
              prose-li:my-1
              prose-hr:border-gray-200 dark:prose-hr:border-gray-700 prose-hr:my-8 // css-check-ignore
              prose-blockquote:border-l-4 prose-blockquote:border-blue-500 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-gray-600 dark:prose-blockquote:text-gray-400 // css-check-ignore
            ">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // Add IDs and hover anchor links to headings
                  h2: ({ children, ...props }) => {
                    const text = String(children);
                    const id = text
                      .toLowerCase()
                      .replace(/[^\w\s-]/g, '')
                      .replace(/\s+/g, '-')
                      .replace(/--+/g, '-');
                    // Check if this is "Common tasks" section
                    const isCommonTasks = text.toLowerCase().includes('common tasks');
                    return (
                      <h2
                        id={id}
                        className={`group${isCommonTasks ? 'bg-info-subtle -mx-4 px-4 py-2 rounded-lg' : ''}`}
                        {...props}
                      >
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
                    // Check for step numbers like "1)" or "Step 1"
                    const stepMatch = text.match(/^(\d+)\)/);
                    return (
                      <h3 id={id} className="group" {...props}>
                        {stepMatch ? (
                          <>
                            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-500 text-white text-sm font-medium mr-2"> {/* css-check-ignore: no semantic token */}
                              {stepMatch[1]}
                            </span>
                            {text.replace(/^\d+\)\s*/, '')}
                          </>
                        ) : (
                          children
                        )}
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
                  // Transform Tip/Note/Warning paragraphs into callout boxes
                  p: ({ children, ...props }) => {
                    const text = String(children);
                    // Check for callout patterns
                    if (text.startsWith('**Tip:**') || text.startsWith('Tip:')) {
                      const content = text.replace(/^\*\*Tip:\*\*\s*|^Tip:\s*/, '');
                      return (
                        <div className="not-prose my-4 flex gap-3 rounded-lg border border-info bg-info-subtle p-4">
                          <Lightbulb className="w-5 h-5 text-info flex-shrink-0 mt-0.5" />
                          <div className="text-sm text-info">{content}</div>
                        </div>
                      );
                    }
                    if (text.startsWith('**Warning:**') || text.startsWith('Warning:')) {
                      const content = text.replace(/^\*\*Warning:\*\*\s*|^Warning:\s*/, '');
                      return (
                        <div className="not-prose my-4 flex gap-3 rounded-lg border border-warning bg-warning-subtle p-4">
                          <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
                          <div className="text-sm text-warning">{content}</div>
                        </div>
                      );
                    }
                    if (text.startsWith('**Note:**') || text.startsWith('Note:')) {
                      const content = text.replace(/^\*\*Note:\*\*\s*|^Note:\s*/, '');
                      return (
                        <div className="not-prose my-4 flex gap-3 rounded-lg border border-primary bg-surface p-4">
                          <Info className="w-5 h-5 text-secondary flex-shrink-0 mt-0.5" />
                          <div className="text-sm text-secondary">{content}</div>
                        </div>
                      );
                    }
                    return <p {...props}>{children}</p>;
                  },
                  // Style ordered list items with step badges
                  ol: ({ children, ...props }) => {
                    // Map children to add index for step badges
                    let index = 0;
                    const enhancedChildren = React.Children.map(children, (child) => {
                      if (React.isValidElement(child) && child.type === 'li') {
                        const currentIndex = index++;
                        return (
                          <li key={currentIndex} className="flex gap-3 items-start">
                            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-500 text-white text-sm font-medium flex-shrink-0"> {/* css-check-ignore: no semantic token */}
                              {currentIndex + 1}
                            </span>
                            <div className="flex-1">{child.props.children}</div>
                          </li>
                        );
                      }
                      return child;
                    });
                    return <ol className="space-y-2 list-none pl-0" {...props}>{enhancedChildren}</ol>;
                  },
                }}
              >
                {doc.content}
              </ReactMarkdown>
            </div>
          </article>
          <Footer />
        </div>
      </div>
    </PageVisibilityGuard>
  );
}
