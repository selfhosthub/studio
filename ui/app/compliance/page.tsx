// ui/app/compliance/page.tsx

export const dynamic = 'force-dynamic';

import { notFound } from 'next/navigation';
import { PublicNavbar, PublicFooter } from '@/widgets/layout';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { isPageVisible, serverFetch } from '@/shared/lib/page-visibility';
import { API_VERSION } from '@/shared/lib/config';

interface Disclosure {
  key: string;
  title: string;
  content: string;
}

async function getDisclosures(): Promise<Disclosure[] | null> {
  const response = await serverFetch(`${API_VERSION}/public/disclosures`, {
    cache: 'no-store',
  } as RequestInit);

  if (response) {
    const data = await response.json();
    return data.disclosures || [];
  }

  return null;
}

export default async function CompliancePage() {
  const visible = await isPageVisible('compliance');
  if (!visible) {
    notFound();
  }

  const disclosures = await getDisclosures();
  if (!disclosures || disclosures.length === 0) {
    notFound();
  }

  return (
    <main className="flex min-h-screen flex-col bg-card">
      <PublicNavbar />

      {/* Hero Section */}
      <section className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white py-16">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto">
            <h1 className="text-4xl md:text-5xl font-bold mb-4">Compliance</h1>
            <p className="text-lg">Service disclosures and compliance information</p>
          </div>
        </div>
      </section>

      {/* Table of Contents */}
      {disclosures.length > 1 && (
        <section className="py-8 border-b border-primary">
          <div className="container mx-auto px-4">
            <div className="max-w-4xl mx-auto">
              <h2 className="text-sm font-semibold text-secondary uppercase tracking-wide mb-3">On This Page</h2>
              <ul className="space-y-1">
                {disclosures.map((disclosure) => (
                  <li key={disclosure.key}>
                    <a
                      href={`#${disclosure.key}`}
                      className="text-info hover:underline"
                    >
                      {disclosure.title}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      )}

      {/* Disclosures */}
      {disclosures.map((disclosure) => (
        <section key={disclosure.key} id={disclosure.key} className="py-0">
          <div className="bg-secondary/10 border-y border-primary py-4">
            <div className="container mx-auto px-4">
              <div className="max-w-4xl mx-auto">
                <h2 className="text-xl font-bold text-primary">{disclosure.title}</h2>
              </div>
            </div>
          </div>
          <div className="container mx-auto px-4">
            <div className="max-w-4xl mx-auto py-10">
              <div className="prose prose-lg dark:prose-invert prose-semantic-lg">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{disclosure.content}</ReactMarkdown>
              </div>
            </div>
          </div>
        </section>
      ))}

      <PublicFooter />
    </main>
  );
}
