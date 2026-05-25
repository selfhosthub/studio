// ui/app/contact/page.tsx

'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Navbar, Footer, PageVisibilityGuard } from '@/widgets/layout';
import { Mail, MapPin, Phone, MessageSquare } from 'lucide-react';
import { useBranding } from '@/entities/organization';
import { getPublicContact, submitPublicContact, type PublicContactInfo } from '@/shared/api';

export default function ContactPage() {
  const { branding } = useBranding();
  const [contactInfo, setContactInfo] = useState<PublicContactInfo>({});
  const [isLoading, setIsLoading] = useState(true);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    company: '',
    subject: '',
    message: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState<'idle' | 'success' | 'error'>('idle');

  useEffect(() => {
    // Fetch organization contact details from API
    const fetchContactInfo = async () => {
      try {
        const data = await getPublicContact();
        setContactInfo(data);
      } catch (error) {
        console.error('Failed to fetch contact info:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchContactInfo();
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitStatus('idle');

    try {
      await submitPublicContact(formData);
      setSubmitStatus('success');
      setFormData({
        name: '',
        email: '',
        company: '',
        subject: '',
        message: ''
      });
    } catch (error) {
      console.error('Form submission error:', error);
      setSubmitStatus('error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const hasContactInfo = contactInfo.email || contactInfo.phone || contactInfo.address;

  return (
    <PageVisibilityGuard page="contact">
    <main className="flex min-h-screen flex-col bg-card">
      <Navbar />

      {/* Hero Section */}
      <section className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white py-20">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <h1 className="text-5xl font-bold mb-6">Get in Touch</h1>
            <p className="text-xl">
              Have a question or want to learn more? We&apos;d love to hear from you.
            </p>
          </div>
        </div>
      </section>

      {/* Contact Content */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className={`max-w-6xl mx-auto ${hasContactInfo ? 'grid grid-cols-1 lg:grid-cols-2 gap-12' : 'max-w-2xl'}`}>
            {/* Contact Information - Only show if we have info */}
            {hasContactInfo && (
              <div>
                <h2 className="text-3xl font-bold mb-8 text-primary">Contact Information</h2>

                <div className="space-y-6 mb-12">
                  {contactInfo.email && (
                    <div className="flex items-start">
                      <div className="w-12 h-12 bg-info-subtle rounded-lg flex items-center justify-center mr-4 flex-shrink-0">
                        <Mail className="w-6 h-6 text-info" />
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold mb-1 text-primary">Email</h3>
                        <a href={`mailto:${contactInfo.email}`} className="text-info hover:underline">
                          {contactInfo.email}
                        </a>
                      </div>
                    </div>
                  )}

                  {contactInfo.phone && (
                    <div className="flex items-start">
                      <div className="w-12 h-12 bg-info-subtle rounded-lg flex items-center justify-center mr-4 flex-shrink-0">
                        <Phone className="w-6 h-6 text-info" />
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold mb-1 text-primary">Phone</h3>
                        <a href={`tel:${contactInfo.phone}`} className="text-info hover:underline">
                          {contactInfo.phone}
                        </a>
                      </div>
                    </div>
                  )}

                  {contactInfo.address && (
                    <div className="flex items-start">
                      <div className="w-12 h-12 bg-info-subtle rounded-lg flex items-center justify-center mr-4 flex-shrink-0">
                        <MapPin className="w-6 h-6 text-info" />
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold mb-1 text-primary">Address</h3>
                        <p className="text-secondary whitespace-pre-line">
                          {contactInfo.address}
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Support Links */}
                <div className="bg-info-subtle p-6 rounded-lg">
                  <h3 className="text-xl font-bold mb-4 text-primary">Quick Help</h3>
                  <div className="space-y-3">
                    <Link href="/support" className="flex items-center text-info hover:underline">
                      <MessageSquare className="w-5 h-5 mr-2" />
                      Visit Support Center
                    </Link>
                  </div>
                </div>
              </div>
            )}

            {/* Contact Form */}
            <div>
              <h2 className="text-3xl font-bold mb-8 text-primary">Send Us a Message</h2>

              <form onSubmit={handleSubmit} className="space-y-6">
                <div>
                  <label htmlFor="name" className="block text-sm font-medium text-secondary mb-2">
                    Name *
                  </label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    value={formData.name}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-secondary mb-2">
                    Email *
                  </label>
                  <input
                    type="email"
                    id="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label htmlFor="company" className="block text-sm font-medium text-secondary mb-2">
                    Company
                  </label>
                  <input
                    type="text"
                    id="company"
                    name="company"
                    value={formData.company}
                    onChange={handleChange}
                    className="w-full px-4 py-3 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label htmlFor="subject" className="block text-sm font-medium text-secondary mb-2">
                    Subject *
                  </label>
                  <select
                    id="subject"
                    name="subject"
                    value={formData.subject}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                  >
                    <option value="">Select a subject</option>
                    <option value="general">General Inquiry</option>
                    <option value="support">Technical Support</option>
                    <option value="feedback">Feedback</option>
                    <option value="other">Other</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="message" className="block text-sm font-medium text-secondary mb-2">
                    Message *
                  </label>
                  <textarea
                    id="message"
                    name="message"
                    value={formData.message}
                    onChange={handleChange}
                    required
                    rows={6}
                    className="w-full px-4 py-3 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                {submitStatus === 'success' && (
                  <div className="bg-success-subtle border border-success text-success px-4 py-3 rounded-md">
                    Thank you for your message! We&apos;ll get back to you soon.
                  </div>
                )}

                {submitStatus === 'error' && (
                  <div className="alert alert-error">
                    Sorry, there was an error sending your message. Please try again.
                  </div>
                )}

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="btn-primary w-full py-3 px-6"
                >
                  {isSubmitting ? 'Sending...' : 'Send Message'}
                </button>
              </form>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </main>
    </PageVisibilityGuard>
  );
}
