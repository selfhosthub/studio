// ui/widgets/layout/Testimonials.tsx

'use client';

import { useEffect, useState } from 'react';
import { useApiStatus } from '@/shared/hooks/useApiStatus';
import { getPublicSiteContent } from '@/shared/api';

interface Testimonial {
  name: string;
  title: string;
  feedback: string;
  avatar_url?: string;
}

const Testimonials = () => {
  const apiStatus = useApiStatus();
  const [testimonials, setTestimonials] = useState<Testimonial[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (apiStatus !== 'up') return;

    const fetchTestimonials = async () => {
      try {
        const data = await getPublicSiteContent('home');
        const content = data.content as Record<string, unknown>;
        if (content?.testimonials && Array.isArray(content.testimonials) && content.testimonials.length > 0) {
          // Limit to maximum 3 testimonials for display
          setTestimonials((content.testimonials as Testimonial[]).slice(0, 3));
        }
      } catch {
        // Silently fail - API may be unreachable
      } finally {
        setIsLoading(false);
      }
    };

    fetchTestimonials();
  }, [apiStatus]);

  // Don't render while loading or when empty
  if (isLoading || testimonials.length === 0) {
    return null;
  }

  return (
    <section className="bg-surface py-20">
      <div className="container mx-auto text-center px-4">
        <h2 className="text-3xl font-bold mb-12 text-primary">What Our Users Say</h2>
        <div className={`grid grid-cols-1 ${testimonials.length === 2 ? 'md:grid-cols-2 max-w-4xl mx-auto' : testimonials.length >= 3 ? 'md:grid-cols-3' : 'max-w-lg mx-auto'} gap-8`}>
          {testimonials.map((testimonial, index) => (
            <div key={index} className="p-8 bg-card rounded-lg shadow-md hover:shadow-lg transition-shadow">
              <div className="flex items-center justify-center mb-4">
                {testimonial.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element -- external avatar URL
                  <img
                    src={testimonial.avatar_url}
                    alt={testimonial.name}
                    className="rounded-full w-10 h-10 object-cover"
                  />
                ) : (
                  <div className="bg-info text-white font-bold rounded-full w-10 h-10 flex items-center justify-center">
                    {testimonial.name.charAt(0)}
                  </div>
                )}
              </div>
              <p className="text-secondary mb-6">&quot;{testimonial.feedback}&quot;</p>
              <div>
                <p className="font-semibold text-primary">{testimonial.name}</p>
                <p className="text-muted">{testimonial.title}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Testimonials;
