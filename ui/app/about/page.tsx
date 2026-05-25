// ui/app/about/page.tsx

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Navbar, Footer, PageVisibilityGuard } from '@/widgets/layout';
import { useBranding } from '@/entities/organization';
import { getPublicTeam, getPublicSiteContent, type PublicTeamMember } from '@/shared/api';

interface AboutStory {
  title?: string;
  subtitle?: string;
  story?: string;
}

export default function AboutPage() {
  const { branding } = useBranding();
  const [teamMembers, setTeamMembers] = useState<PublicTeamMember[]>([]);
  const [aboutStory, setAboutStory] = useState<AboutStory>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [teamData, storyData] = await Promise.all([
          getPublicTeam().catch(() => null),
          getPublicSiteContent('about').catch(() => null),
        ]);

        if (teamData) {
          setTeamMembers(teamData);
        }

        if (storyData?.content) {
          setAboutStory(storyData.content as AboutStory);
        }
      } catch (error) {
        console.error('Failed to fetch about data:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, []);

  return (
    <PageVisibilityGuard page="about">
    <main className="flex min-h-screen flex-col bg-card">
      <Navbar />

      {/* Hero Section */}
      <section className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white py-20">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            {branding.companyName && (
              <h1 className="text-5xl font-bold mb-6">About {branding.companyName}</h1>
            )}
            {branding.tagline && (
              <p className="text-xl leading-relaxed">
                {branding.tagline}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* Story Section */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-3xl font-bold mb-8 text-primary">
              {aboutStory.title || 'Our Story'}
            </h2>
            {aboutStory.subtitle && (
              <p className="text-xl text-secondary mb-8">
                {aboutStory.subtitle}
              </p>
            )}
            <div className="space-y-6 text-lg text-secondary leading-relaxed whitespace-pre-line">
              {aboutStory.story || (branding.companyName
                ? `${branding.companyName} was built to give you complete control over your workflows without sacrificing modern features and ease of use.`
                : ''
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Team Section - Only shows if there are public team members */}
      {!isLoading && teamMembers.length > 0 && (
        <section className="bg-surface py-20">
          <div className="container mx-auto px-4">
            <div className="max-w-6xl mx-auto">
              <h2 className="text-3xl font-bold mb-12 text-center text-primary">Meet Our Team</h2>
              <div className={`grid grid-cols-1 md:grid-cols-2 ${teamMembers.length >= 4 ? 'lg:grid-cols-4' : teamMembers.length === 3 ? 'lg:grid-cols-3' : ''} gap-8 justify-center`}>
                {teamMembers.map((member) => (
                  <div key={member.id} className="bg-card p-6 rounded-lg shadow-sm">
                    <div className="w-20 h-20 bg-gradient-to-br from-blue-400 to-indigo-500 rounded-full mx-auto mb-4 flex items-center justify-center text-white text-2xl font-bold">
                      {member.first_name[0]}{member.last_name[0]}
                    </div>
                    <h3 className="text-xl font-bold text-center mb-1 text-primary">
                      {member.first_name} {member.last_name}
                    </h3>
                    <p className="text-info text-center text-sm mb-3">{member.role}</p>
                    {member.bio && (
                      <p className="text-secondary text-sm text-center">{member.bio}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* CTA Section */}
      <section className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white py-20">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold mb-6">Get in Touch</h2>
          <p className="text-xl mb-8 max-w-2xl mx-auto">
            Have questions or want to learn more? We&apos;d love to hear from you.
          </p>
          <Link
            href="/contact"
            className="inline-block bg-card text-info px-8 py-4 rounded-md text-lg font-semibold hover:bg-card transition-colors"
          >
            Contact Us
          </Link>
        </div>
      </section>

      <Footer />
    </main>
    </PageVisibilityGuard>
  );
}
