// ui/app/support/page.tsx

'use client';

import Link from 'next/link';
import { Navbar, Footer, PageVisibilityGuard } from '@/widgets/layout';
import { Book, Mail } from 'lucide-react';

const resources = [
  {
    icon: Book,
    title: 'Documentation',
    description: 'Comprehensive guides, API references, and tutorials',
    link: '/docs',
    color: 'blue'
  },
  {
    icon: Mail,
    title: 'Email Support',
    description: 'Get help from our support team',
    link: '/contact',
    color: 'orange'
  }
];

export default function SupportPage() {
  return (
    <PageVisibilityGuard page="support">
    <main className="flex min-h-screen flex-col bg-card">
      <Navbar />

      {/* Hero Section */}
      <section className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white py-20"> {/* css-check-ignore: no semantic token */}
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <h1 className="text-5xl font-bold mb-6">How Can We Help?</h1>
            <p className="text-xl mb-8">
              Browse documentation or get in touch with our support team.
            </p>
          </div>
        </div>
      </section>

      {/* Support Resources */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="max-w-6xl mx-auto">
            <h2 className="text-3xl font-bold mb-12 text-center text-primary">
              Support Resources
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl mx-auto">
              {resources.map((resource, index) => {
                const Icon = resource.icon;
                const colorClasses = {
                  blue: 'bg-info-subtle text-info',
                  purple: 'bg-purple-100 dark:bg-purple-900 text-purple-600 dark:text-purple-400', // css-check-ignore: no semantic token
                  green: 'bg-success-subtle text-success',
                  orange: 'bg-orange-100 dark:bg-orange-900 text-orange-600 dark:text-orange-400' // css-check-ignore: no semantic token
                };

                return (
                  <Link
                    key={index}
                    href={resource.link}
                    className="bg-card p-6 rounded-lg shadow-md hover:shadow-xl transition-shadow border border-primary group"
                  >
                    <div className={`w-12 h-12 rounded-lg flex items-center justify-center mb-4 ${colorClasses[resource.color as keyof typeof colorClasses]}`}>
                      <Icon className="w-6 h-6" />
                    </div>
                    <h3 className="text-xl font-bold mb-2 text-primary group-hover:text-info transition-colors">
                      {resource.title}
                    </h3>
                    <p className="text-secondary">{resource.description}</p>
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* Contact Support CTA */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <h2 className="text-3xl font-bold mb-6 text-primary">
              Still Need Help?
            </h2>
            <p className="text-xl text-secondary mb-8">
              Our support team is here to help. Get in touch and we&apos;ll respond as soon as possible.
            </p>
            <div className="flex flex-col sm:flex-row justify-center gap-4">
              <Link
                href="/contact"
                className="btn-primary px-8 py-4 text-lg"
              >
                Contact Support
              </Link>
              <Link
                href="/docs"
                className="bg-card text-info px-8 py-4 rounded-md text-lg font-semibold border-2 border-info hover:bg-info-subtle transition-colors"
              >
                Browse Documentation
              </Link>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </main>
    </PageVisibilityGuard>
  );
}
