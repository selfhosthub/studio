// ui/app/features/page.tsx

'use client';

import Link from 'next/link';
import { Navbar, Footer } from '@/widgets/layout';
import { Workflow, Users, Shield, Zap, BarChart3, Globe } from 'lucide-react';
const features = [
  {
    icon: Workflow,
    title: 'Workflow Automation',
    description: 'Build custom workflows with our visual flow editor. Automate repetitive tasks and streamline your production pipeline.',
    benefits: [
      'Drag-and-drop flow builder',
      'Custom triggers and actions',
      'Conditional logic support',
      'Real-time execution monitoring'
    ]
  },
  {
    icon: Users,
    title: 'Team Collaboration',
    description: 'Work seamlessly with your team. Share resources, assign tasks, and track progress in real-time.',
    benefits: [
      'Role-based access control',
      'Real-time notifications',
      'Team activity tracking',
      'Shared resource management'
    ]
  },
  {
    icon: Shield,
    title: 'Enterprise Security',
    description: 'Keep your data secure with enterprise-grade security features. Self-host on your own infrastructure.',
    benefits: [
      'Self-hosted deployment',
      'End-to-end encryption',
      'API key management',
      'Audit logs and compliance'
    ]
  },
  {
    icon: Zap,
    title: 'High Performance',
    description: 'Built for speed and reliability. Handle large-scale productions with ease and confidence.',
    benefits: [
      'Lightning-fast response times',
      'Scalable architecture',
      'Optimized resource usage',
      ' 99.9% uptime guarantee'
    ]
  },
  {
    icon: BarChart3,
    title: 'Analytics & Insights',
    description: 'Make data-driven decisions with comprehensive analytics and reporting tools.',
    benefits: [
      'Real-time dashboards',
      'Custom reports',
      'Usage metrics',
      'Performance tracking'
    ]
  },
  {
    icon: Globe,
    title: 'Provider Integration',
    description: 'Connect with popular media services and providers. Extend functionality with custom integrations.',
    benefits: [
      'Pre-built integrations',
      'Custom provider support',
      'Webhook support',
      'REST API access'
    ]
  }
];

export default function FeaturesPage() {
  return (
    <main className="flex min-h-screen flex-col bg-card">
      <Navbar />

      {/* Hero Section */}
      <section className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white py-20"> {/* css-check-ignore: no semantic token */}
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <h1 className="text-5xl font-bold mb-6">Powerful Features for Modern Studios</h1>
            <p className="text-xl mb-8">
              Everything you need to streamline your media production workflow and scale your operations.
            </p>
            <Link
              href="/register"
              className="inline-block bg-card text-info px-8 py-4 rounded-md text-lg font-semibold hover:bg-card transition-colors"
            >
              Get Started
            </Link>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature, index) => {
              const Icon = feature.icon;
              return (
                <div
                  key={index}
                  className="bg-card p-8 rounded-lg shadow-md hover:shadow-xl transition-shadow border border-primary"
                >
                  <div className="w-12 h-12 bg-info-subtle rounded-lg flex items-center justify-center mb-4">
                    <Icon className="w-6 h-6 text-info" />
                  </div>
                  <h3 className="text-xl font-bold mb-3 text-primary">{feature.title}</h3>
                  <p className="text-secondary mb-4">{feature.description}</p>
                  <ul className="space-y-2">
                    {feature.benefits.map((benefit, idx) => (
                      <li key={idx} className="flex items-start text-sm text-secondary">
                        <svg className="w-5 h-5 text-success mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        {benefit}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="bg-surface py-20">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold mb-6 text-primary">Ready to get started?</h2>
          <p className="text-xl text-secondary mb-8 max-w-2xl mx-auto">
            Join thousands of studios already using Self-Host Studio to streamline their workflows.
          </p>
          <div className="flex flex-col sm:flex-row justify-center gap-4">
            <Link
              href="/register"
              className="btn-primary inline-flex items-center justify-center px-8 py-4 text-lg"
            >
              Get Started
            </Link>
          </div>
        </div>
      </section>

      <Footer />
    </main>
  );
}
