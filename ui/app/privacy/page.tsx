// ui/app/privacy/page.tsx

export const dynamic = 'force-dynamic';

import { notFound } from 'next/navigation';
import { PublicNavbar, PublicFooter } from '@/widgets/layout';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { isPageVisible, serverFetch } from '@/shared/lib/page-visibility';
import { API_VERSION } from '@/shared/lib/config';

interface PrivacyContent {
  content: string;
  last_updated: string;
}

async function getPrivacyContent(): Promise<PrivacyContent | null> {
  const response = await serverFetch(`${API_VERSION}/public/site-content/privacy`, {
    cache: 'no-store',
  } as RequestInit);

  if (response) {
    const data = await response.json();
    if (data.content?.content) {
      return {
        content: data.content.content,
        last_updated: data.content.last_updated || '',
      };
    }
  }

  return null;
}

export default async function PrivacyPage() {
  const visible = await isPageVisible('privacy');
  if (!visible) {
    notFound();
  }

  const content = await getPrivacyContent();
  if (!content) {
    notFound();
  }

  return (
    <main className="flex min-h-screen flex-col bg-card">
      <PublicNavbar />

      {/* Hero Section */}
      <section className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white py-16">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto">
            <h1 className="text-4xl md:text-5xl font-bold mb-4">Privacy Policy</h1>
            {content.last_updated && (
              <p className="text-lg opacity-90">Last updated: {content.last_updated}</p>
            )}
          </div>
        </div>
      </section>

      {/* Content */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto prose prose-lg dark:prose-invert prose-semantic-lg">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content.content}</ReactMarkdown>
          </div>
        </div>
      </section>

      <PublicFooter />
    </main>
  );
}
