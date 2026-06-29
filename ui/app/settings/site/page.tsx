// ui/app/settings/site/page.tsx

'use client';

import { MarkdownEditor } from '@/shared/ui/MarkdownEditor';
import { MediaPicker } from '@/features/files';
import { useSiteSettings } from './hooks/useSiteSettings';
import type { TabId, PageVisibility } from './types';

const AVAILABLE_ICONS = [
  { value: 'workflow', label: 'Workflow' },
  { value: 'brain', label: 'Brain / AI' },
  { value: 'image', label: 'Image' },
  { value: 'video', label: 'Video' },
  { value: 'music', label: 'Music' },
  { value: 'mic', label: 'Microphone' },
  { value: 'bot', label: 'Bot' },
  { value: 'sparkles', label: 'Sparkles' },
  { value: 'zap', label: 'Zap' },
  { value: 'settings', label: 'Settings' },
  { value: 'shield', label: 'Shield' },
  { value: 'globe', label: 'Globe' },
  { value: 'layers', label: 'Layers' },
  { value: 'git-branch', label: 'Git Branch' },
  { value: 'database', label: 'Database' },
  { value: 'cloud', label: 'Cloud' },
  { value: 'lock', label: 'Lock' },
  { value: 'monitor', label: 'Monitor' },
  { value: 'cpu', label: 'CPU' },
  { value: 'plug', label: 'Plug' },
];

const tabs: { id: TabId; label: string }[] = [
  { id: 'visibility', label: 'Page Visibility' },
  { id: 'hero', label: 'Hero Section' },
  { id: 'compliance', label: 'Subscription Compliance' },
  { id: 'disclosures', label: 'Disclosures' },
  { id: 'features', label: 'Feature Blocks' },
  { id: 'testimonials', label: 'Testimonials' },
  { id: 'about', label: 'About Story' },
  { id: 'contact', label: 'Contact Info' },
  { id: 'privacy', label: 'Privacy Policy' },
  { id: 'terms', label: 'Terms of Service' },
];

export default function SiteSettingsPage() {
  const s = useSiteSettings();

  if (s.accessLoading || s.isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="spinner-md"></div>
          <p className="mt-2 text-sm text-muted">Loading site settings...</p>
        </div>
      </div>
    );
  }

  if (!s.hasAccess) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card">
        <h2 className="section-title">Site Content Management</h2>
        <p className="mt-1 text-sm text-muted">
          Manage public-facing content including testimonials, terms of service, privacy policy, and more.
        </p>
      </div>

      {/* Tabs */}
      <div className="card !p-0">
        <div className="border-b border-primary">
          <nav
            className="-mb-px flex space-x-4 sm:space-x-8 overflow-x-auto scrollbar-hide px-6"
            aria-label="Tabs"
          >
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => s.setActiveTab(tab.id)}
                className={`${
                  s.activeTab === tab.id
                    ? 'border-info text-info'
                    : 'border-transparent text-muted hover:text-primary hover:border-primary'
                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex-shrink-0`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="p-6">
          {/* Testimonials Tab */}
          {s.activeTab === 'testimonials' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="section-title">Home Page Testimonials</h3>
                  <p className="mt-1 text-sm text-muted">
                    Manage customer testimonials displayed on the home page.
                  </p>
                </div>
                <button onClick={s.addTestimonial} className="btn-primary">
                  Add Testimonial
                </button>
              </div>

              {s.testimonials.length === 0 ? (
                <p className="text-sm text-muted py-4">
                  No testimonials yet. Click &quot;Add Testimonial&quot; to create one.
                </p>
              ) : (
                <div className="space-y-4">
                  {s.testimonials.map((testimonial, index) => (
                    <div key={index} className="card-section">
                      <div className="flex justify-between items-start mb-4">
                        <span className="text-sm font-medium text-secondary">
                          Testimonial #{index + 1}
                        </span>
                        <button onClick={() => s.removeTestimonial(index)} className="link-danger text-sm">
                          Remove
                        </button>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label htmlFor={`testimonial-name-${index}`} className="form-label">Name</label>
                          <input
                            id={`testimonial-name-${index}`}
                            type="text"
                            value={testimonial.name}
                            onChange={(e) => s.updateTestimonial(index, 'name', e.target.value)}
                            className="form-input"
                            placeholder="John Doe"
                          />
                        </div>
                        <div>
                          <label htmlFor={`testimonial-title-${index}`} className="form-label">Title / Role</label>
                          <input
                            id={`testimonial-title-${index}`}
                            type="text"
                            value={testimonial.title}
                            onChange={(e) => s.updateTestimonial(index, 'title', e.target.value)}
                            className="form-input"
                            placeholder="Studio Manager"
                          />
                        </div>
                        <div className="md:col-span-2">
                          <label htmlFor={`testimonial-feedback-${index}`} className="form-label">Feedback</label>
                          <textarea
                            id={`testimonial-feedback-${index}`}
                            value={testimonial.feedback}
                            onChange={(e) => s.updateTestimonial(index, 'feedback', e.target.value)}
                            rows={3}
                            className="form-textarea"
                            placeholder="Their testimonial..."
                          />
                        </div>
                        <div className="md:col-span-2">
                          <label htmlFor={`testimonial-avatar-${index}`} className="form-label">Avatar URL (optional)</label>
                          <input
                            id={`testimonial-avatar-${index}`}
                            type="text"
                            value={testimonial.avatar_url || ''}
                            onChange={(e) => s.updateTestimonial(index, 'avatar_url', e.target.value)}
                            className="form-input"
                            placeholder="https://example.com/avatar.jpg"
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Hero Section Tab */}
          {s.activeTab === 'hero' && (
            <div className="space-y-6">
              <div>
                <h3 className="section-title">Hero Section</h3>
                <p className="mt-1 text-sm text-muted">
                  Customize the hero banner on the home page. Leave fields empty to use defaults from branding settings.
                </p>
              </div>

              <div className="card-section flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-medium text-primary">Show Hero Section</h4>
                  <p className="text-sm text-muted">Toggle the hero banner visibility on the home page</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={s.heroConfig.visible}
                    onChange={(e) =>
                      s.setHeroConfig((prev) => ({ ...prev, visible: e.target.checked }))
                    }
                    className="sr-only peer"
                  />
                  <div className="toggle-switch"></div>
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="md:col-span-2">
                  <label htmlFor="hero-headline" className="form-label">Headline</label>
                  <input
                    id="hero-headline"
                    type="text"
                    value={s.heroConfig.headline || ''}
                    onChange={(e) =>
                      s.setHeroConfig((prev) => ({ ...prev, headline: e.target.value || null }))
                    }
                    className="form-input"
                    placeholder="Leave empty to use company name from branding"
                  />
                </div>
                <div className="md:col-span-2">
                  <label htmlFor="hero-subtext" className="form-label">Subtext</label>
                  <textarea
                    id="hero-subtext"
                    value={s.heroConfig.subtext || ''}
                    onChange={(e) =>
                      s.setHeroConfig((prev) => ({ ...prev, subtext: e.target.value || null }))
                    }
                    rows={3}
                    className="form-textarea"
                    placeholder="Leave empty to use tagline from branding"
                  />
                </div>
                <div>
                  <label htmlFor="hero-cta-text" className="form-label">CTA Button Text</label>
                  <input
                    id="hero-cta-text"
                    type="text"
                    value={s.heroConfig.cta_text || ''}
                    onChange={(e) =>
                      s.setHeroConfig((prev) => ({ ...prev, cta_text: e.target.value || null }))
                    }
                    className="form-input"
                    placeholder="Get Started"
                  />
                </div>
                <div>
                  <label htmlFor="hero-cta-link" className="form-label">CTA Button Link</label>
                  <select
                    id="hero-cta-link"
                    value={s.heroConfig.cta_link || ''}
                    onChange={(e) =>
                      s.setHeroConfig((prev) => ({ ...prev, cta_link: e.target.value || null }))
                    }
                    className="form-select w-full"
                  >
                    <option value="">None (hidden)</option>
                    <option value="/register">Register</option>
                    <option value="/pricing">Pricing</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Features Tab */}
          {s.activeTab === 'features' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="section-title">Home Page Feature Blocks</h3>
                  <p className="mt-1 text-sm text-muted">
                    Manage feature blocks displayed on the home page. Drag to reorder.
                  </p>
                </div>
                <button onClick={s.addFeature} className="btn-primary">
                  Add Feature
                </button>
              </div>

              {s.features.length === 0 ? (
                <p className="text-sm text-muted py-4">
                  No features yet. Click &quot;Add Feature&quot; to create one.
                </p>
              ) : (
                <div className="space-y-4">
                  {s.features.map((feature, index) => (
                    <div key={feature.id} className="card-section">
                      <div className="flex justify-between items-start mb-4">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-secondary">
                            Feature #{index + 1}
                          </span>
                          <div className="flex gap-1">
                            <button
                              type="button"
                              onClick={() => s.moveFeature(index, 'up')}
                              disabled={index === 0}
                              className="btn-icon-sm"
                              title="Move up"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                              </svg>
                            </button>
                            <button
                              type="button"
                              onClick={() => s.moveFeature(index, 'down')}
                              disabled={index === s.features.length - 1}
                              className="btn-icon-sm"
                              title="Move down"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                              </svg>
                            </button>
                          </div>
                        </div>
                        <button onClick={() => s.removeFeature(index)} className="link-danger text-sm">
                          Remove
                        </button>
                      </div>
                      {/* Visible toggle */}
                      <div className="flex items-center justify-between mb-4 pb-4 border-b border-primary">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-secondary">Visible on homepage</span>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={feature.visible !== false}
                            onChange={(e) => s.updateFeature(index, 'visible', e.target.checked)}
                            className="sr-only peer"
                          />
                          <div className="toggle-switch toggle-switch-sm"></div>
                        </label>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label htmlFor={`feature-title-${index}`} className="form-label">Title</label>
                          <input
                            id={`feature-title-${index}`}
                            type="text"
                            value={feature.title}
                            onChange={(e) => s.updateFeature(index, 'title', e.target.value)}
                            className="form-input"
                            placeholder="Feature title"
                          />
                        </div>
                        <div>
                          <label htmlFor={`feature-icon-${index}`} className="form-label">Icon</label>
                          <select
                            id={`feature-icon-${index}`}
                            value={feature.icon || ''}
                            onChange={(e) => s.updateFeature(index, 'icon', e.target.value || null)}
                            className="form-select w-full"
                          >
                            <option value="">No icon</option>
                            {AVAILABLE_ICONS.map(({ value, label }) => (
                              <option key={value} value={value}>{label}</option>
                            ))}
                          </select>
                          <p className="form-helper mt-1">Shown when no thumbnail is set</p>
                        </div>
                        <div className="md:col-span-2">
                          <label htmlFor={`feature-description-${index}`} className="form-label">Description</label>
                          <textarea
                            id={`feature-description-${index}`}
                            value={feature.description}
                            onChange={(e) => s.updateFeature(index, 'description', e.target.value)}
                            rows={3}
                            className="form-textarea"
                            placeholder="Feature description..."
                          />
                        </div>
                        <div>
                          <label htmlFor={`feature-media-type-${index}`} className="form-label">Media Type</label>
                          <select
                            id={`feature-media-type-${index}`}
                            value={feature.media_type}
                            onChange={(e) => s.updateFeature(index, 'media_type', e.target.value as 'image' | 'video')}
                            className="form-select w-full"
                          >
                            <option value="image">Image</option>
                            <option value="video">Video</option>
                          </select>
                        </div>
                        <div className="md:col-span-2">
                          <div className="flex items-end gap-2">
                            <div className="flex-1">
                              <MediaPicker
                                value={feature.thumbnail}
                                onChange={(path, mediaType) => {
                                  s.updateFeature(index, 'thumbnail', path);
                                  s.updateFeature(index, 'media_type', mediaType);
                                }}
                                label="Thumbnail / Media (optional)"
                                mediaTypeFilter={feature.media_type}
                              />
                            </div>
                            {feature.thumbnail && (
                              <button
                                type="button"
                                onClick={() => {
                                  s.updateFeature(index, 'thumbnail', '');
                                }}
                                className="link-danger text-sm mb-1"
                                title="Remove thumbnail"
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        </div>
                        <div className="md:col-span-2">
                          <label htmlFor={`feature-workflow-${index}`} className="form-label">
                            Workflow Link
                            <span className="ml-2 text-xs text-muted">(Coming Soon)</span>
                          </label>
                          <input
                            id={`feature-workflow-${index}`}
                            type="text"
                            value={feature.workflow_id || ''}
                            disabled
                            className="form-input-readonly"
                            placeholder="Workflow integration coming soon..."
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Terms Tab */}
          {s.activeTab === 'terms' && (
            <div className="space-y-6">
              <div>
                <h3 className="section-title">Terms of Service</h3>
                <p className="mt-1 text-sm text-muted">
                  Edit the Terms of Service content. Supports Markdown formatting.
                </p>
              </div>
              <div>
                <label htmlFor="terms-last-updated" className="form-label">Last Updated Date</label>
                <input
                  id="terms-last-updated"
                  type="text"
                  value={s.termsLastUpdated}
                  onChange={(e) => s.setTermsLastUpdated(e.target.value)}
                  className="form-input max-w-xs"
                  placeholder="January 1, 2025"
                />
              </div>
              <div>
                <label htmlFor="terms-content" className="form-label">Content (Markdown)</label>
                <MarkdownEditor
                  id="terms-content"
                  value={s.termsContent}
                  onChange={s.setTermsContent}
                  placeholder="# Terms of Service&#10;&#10;Your terms content here..."
                />
              </div>
            </div>
          )}

          {/* Privacy Tab */}
          {s.activeTab === 'privacy' && (
            <div className="space-y-6">
              <div>
                <h3 className="section-title">Privacy Policy</h3>
                <p className="mt-1 text-sm text-muted">
                  Edit the Privacy Policy content. Supports Markdown formatting.
                </p>
              </div>
              <div>
                <label htmlFor="privacy-last-updated" className="form-label">Last Updated Date</label>
                <input
                  id="privacy-last-updated"
                  type="text"
                  value={s.privacyLastUpdated}
                  onChange={(e) => s.setPrivacyLastUpdated(e.target.value)}
                  className="form-input max-w-xs"
                  placeholder="January 1, 2025"
                />
              </div>
              <div>
                <label htmlFor="privacy-content" className="form-label">Content (Markdown)</label>
                <MarkdownEditor
                  id="privacy-content"
                  value={s.privacyContent}
                  onChange={s.setPrivacyContent}
                  placeholder="# Privacy Policy&#10;&#10;Your privacy policy content here..."
                />
              </div>
            </div>
          )}

          {/* Contact Tab */}
          {s.activeTab === 'contact' && (
            <div className="space-y-6">
              <div>
                <h3 className="section-title">Contact Information</h3>
                <p className="mt-1 text-sm text-muted">
                  Set the contact information displayed on the Contact page. Leave fields empty to hide them.
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label htmlFor="contact-email" className="form-label">Email Address</label>
                  <input
                    id="contact-email"
                    type="email"
                    value={s.contactEmail}
                    onChange={(e) => s.setContactEmail(e.target.value)}
                    className="form-input"
                    placeholder="contact@example.com"
                  />
                </div>
                <div>
                  <label htmlFor="contact-phone" className="form-label">Phone Number</label>
                  <input
                    id="contact-phone"
                    type="text"
                    value={s.contactPhone}
                    onChange={(e) => s.setContactPhone(e.target.value)}
                    className="form-input"
                    placeholder="+1 (555) 123-4567"
                  />
                </div>
                <div className="md:col-span-2">
                  <label htmlFor="contact-address" className="form-label">Address</label>
                  <textarea
                    id="contact-address"
                    value={s.contactAddress}
                    onChange={(e) => s.setContactAddress(e.target.value)}
                    rows={3}
                    className="form-textarea"
                    placeholder="123 Business Street&#10;City, State 12345&#10;Country"
                  />
                </div>
              </div>
            </div>
          )}

          {/* About Tab */}
          {s.activeTab === 'about' && (
            <div className="space-y-6">
              <div>
                <h3 className="section-title">About Page Story</h3>
                <p className="mt-1 text-sm text-muted">
                  Edit the story section displayed on the About page.
                </p>
              </div>
              <div>
                <label htmlFor="about-title" className="form-label">Title</label>
                <input
                  id="about-title"
                  type="text"
                  value={s.aboutTitle}
                  onChange={(e) => s.setAboutTitle(e.target.value)}
                  className="form-input w-full"
                  placeholder="Our Story"
                />
              </div>
              <div>
                <label htmlFor="about-subtitle" className="form-label">Subtitle</label>
                <input
                  id="about-subtitle"
                  type="text"
                  value={s.aboutSubtitle}
                  onChange={(e) => s.setAboutSubtitle(e.target.value)}
                  className="form-input w-full"
                  placeholder="A brief tagline or subtitle"
                />
              </div>
              <div>
                <label htmlFor="about-story" className="form-label">Story Content</label>
                <textarea
                  id="about-story"
                  value={s.aboutStory}
                  onChange={(e) => s.setAboutStory(e.target.value)}
                  rows={10}
                  className="form-textarea"
                  placeholder="Tell your company's story..."
                />
              </div>
            </div>
          )}

          {/* Visibility Tab */}
          {s.activeTab === 'visibility' && (
            <div className="space-y-6">
              <div>
                <h3 className="section-title">Page Visibility</h3>
                <p className="mt-1 text-sm text-muted">
                  Control which public pages are visible on the site. Disabled pages will show a 404 error.
                </p>
              </div>

              <div className="alert alert-info">
                <p className="text-sm alert-info-text">
                  <strong>Note:</strong> The Pricing page visibility is controlled by your billing configuration.
                  When billing plans are created, the Pricing page is automatically enabled.
                  Manage plans under <strong>Billing → Plans</strong>.
                </p>
              </div>

              <div className="space-y-4">
                {[
                  { key: 'about', label: 'About', description: 'Company information and team page' },
                  { key: 'compliance', label: 'Compliance', description: 'Compliance disclosures (SMS consent, etc.)' },
                  { key: 'contact', label: 'Contact', description: 'Contact form and information' },
                  { key: 'docs', label: 'Documentation', description: 'Product documentation' },
                  { key: 'privacy', label: 'Privacy Policy', description: 'Privacy policy page' },
                  { key: 'support', label: 'Support', description: 'Support and help resources' },
                  { key: 'terms', label: 'Terms of Service', description: 'Terms of service page' },
                  { key: 'blueprints', label: 'Blueprints', description: 'Blueprint vision page in the dashboard sidebar (coming soon feature)' },
                ].map(({ key, label, description }) => (
                  <div
                    key={key}
                    className="card-section flex items-center justify-between"
                  >
                    <div>
                      <h4 className="text-sm font-medium text-primary">{label}</h4>
                      <p className="text-sm text-muted">{description}</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={s.pageVisibility[key as keyof PageVisibility]}
                        onChange={(e) =>
                          s.setPageVisibility((prev) => ({
                            ...prev,
                            [key]: e.target.checked,
                          }))
                        }
                        className="sr-only peer"
                      />
                      <div className="toggle-switch"></div>
                    </label>
                  </div>
                ))}
              </div>

              {/* Registration Toggle */}
              <div className="mt-6 pt-6 border-t border-primary">
                <h3 className="section-title mb-1">Registration</h3>
                <p className="text-sm text-muted mb-4">
                  Control whether new users can register accounts on this platform.
                </p>
                <div className="card-section flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-medium text-primary">Allow New Registrations</h4>
                    <p className="text-sm text-muted">When disabled, the Sign Up button and registration page are hidden</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={s.allowRegistration}
                      onChange={(e) => s.setAllowRegistration(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="toggle-switch"></div>
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* Compliance Tab */}
          {s.activeTab === 'compliance' && (
            <div className="space-y-6">
              <div>
                <h3 className="section-title">Subscription Compliance (ROSCA)</h3>
                <p className="mt-1 text-sm text-muted">
                  Configure subscription disclosure text for ROSCA compliance. These texts are shown to users
                  before they commit to a recurring subscription.
                </p>
                <p className="mt-2 form-helper">
                  Supported placeholders: {'{trial_days}'}, {'{trial_end_date}'}, {'{price}'}, {'{interval}'}, {'{plan_name}'}
                </p>
              </div>

              <div className="alert alert-info flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-medium text-primary">Enable ROSCA Compliance Mode</h4>
                  <p className="text-sm text-muted">
                    When enabled, subscription disclosure text will be shown at registration and checkout.
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={s.complianceSettings.rosca_enabled}
                    onChange={(e) =>
                      s.setComplianceSettings((prev) => ({
                        ...prev,
                        rosca_enabled: e.target.checked,
                      }))
                    }
                    className="sr-only peer"
                  />
                  <div className="toggle-switch"></div>
                </label>
              </div>

              <div className="space-y-2">
                <label htmlFor="compliance-trial-disclosure" className="form-label !mb-0">Trial Disclosure</label>
                <p className="form-helper">
                  Shown when a user signs up with a free trial. Explains what happens when the trial ends.
                </p>
                <textarea
                  id="compliance-trial-disclosure"
                  value={s.complianceSettings.trial_disclosure}
                  onChange={(e) =>
                    s.setComplianceSettings((prev) => ({
                      ...prev,
                      trial_disclosure: e.target.value,
                    }))
                  }
                  rows={3}
                  className="form-textarea text-sm"
                  placeholder="After your {trial_days}-day free trial ends..."
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="compliance-recurring-disclosure" className="form-label !mb-0">Recurring Subscription Disclosure</label>
                <p className="form-helper">
                  Shown when a user subscribes without a trial. Explains the recurring charge.
                </p>
                <textarea
                  id="compliance-recurring-disclosure"
                  value={s.complianceSettings.recurring_disclosure}
                  onChange={(e) =>
                    s.setComplianceSettings((prev) => ({
                      ...prev,
                      recurring_disclosure: e.target.value,
                    }))
                  }
                  rows={2}
                  className="form-textarea text-sm"
                  placeholder="You will be charged {price} today..."
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="compliance-one-time-disclosure" className="form-label !mb-0">One-time Payment Disclosure</label>
                <p className="form-helper">
                  Shown for one-time purchases (not subscriptions).
                </p>
                <textarea
                  id="compliance-one-time-disclosure"
                  value={s.complianceSettings.one_time_disclosure}
                  onChange={(e) =>
                    s.setComplianceSettings((prev) => ({
                      ...prev,
                      one_time_disclosure: e.target.value,
                    }))
                  }
                  rows={2}
                  className="form-textarea text-sm"
                  placeholder="This is a one-time payment of {price}..."
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="compliance-cancellation-instructions" className="form-label !mb-0">Cancellation Instructions</label>
                <p className="form-helper">
                  Tells users how to cancel their subscription. Required for ROSCA compliance.
                </p>
                <textarea
                  id="compliance-cancellation-instructions"
                  value={s.complianceSettings.cancellation_instructions}
                  onChange={(e) =>
                    s.setComplianceSettings((prev) => ({
                      ...prev,
                      cancellation_instructions: e.target.value,
                    }))
                  }
                  rows={2}
                  className="form-textarea text-sm"
                  placeholder="You can cancel anytime from your account Settings..."
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="compliance-consent-checkbox-text" className="form-label !mb-0">Consent Checkbox Text</label>
                <p className="form-helper">
                  Text shown next to the consent checkbox at checkout.
                </p>
                <textarea
                  id="compliance-consent-checkbox-text"
                  value={s.complianceSettings.consent_checkbox_text}
                  onChange={(e) =>
                    s.setComplianceSettings((prev) => ({
                      ...prev,
                      consent_checkbox_text: e.target.value,
                    }))
                  }
                  rows={2}
                  className="form-textarea text-sm"
                  placeholder="I understand this is a recurring subscription..."
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="compliance-registration-disclosure" className="form-label !mb-0">Registration Page Disclosure</label>
                <p className="form-helper">
                  Shown on the registration page when a plan is pre-selected.
                </p>
                <textarea
                  id="compliance-registration-disclosure"
                  value={s.complianceSettings.registration_disclosure}
                  onChange={(e) =>
                    s.setComplianceSettings((prev) => ({
                      ...prev,
                      registration_disclosure: e.target.value,
                    }))
                  }
                  rows={3}
                  className="form-textarea text-sm"
                  placeholder="By creating an account with the {plan_name} plan..."
                />
              </div>
            </div>
          )}

          {s.activeTab === 'disclosures' && (
            <div className="space-y-6">
              <div>
                <h3 className="section-title">Compliance Disclosures</h3>
                <p className="mt-1 text-sm text-muted">
                  Manage compliance disclosure blocks displayed on the public <strong>/compliance</strong> page.
                  Toggle each disclosure on or off and customize the content as needed.
                </p>
              </div>

              {s.disclosures.map((disclosure, index) => (
                <div key={disclosure.key} className="card-section space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex flex-col gap-0.5">
                        <button
                          type="button"
                          onClick={() => {
                            if (index === 0) return;
                            const updated = [...s.disclosures];
                            [updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
                            s.setDisclosures(updated);
                          }}
                          disabled={index === 0}
                          className="p-0.5 text-muted hover:text-primary disabled:opacity-30"
                          title="Move up"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m18 15-6-6-6 6"/></svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (index === s.disclosures.length - 1) return;
                            const updated = [...s.disclosures];
                            [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
                            s.setDisclosures(updated);
                          }}
                          disabled={index === s.disclosures.length - 1}
                          className="p-0.5 text-muted hover:text-primary disabled:opacity-30"
                          title="Move down"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
                        </button>
                      </div>
                      <div>
                        <input
                          type="text"
                          value={disclosure.title}
                          onChange={(e) => {
                            const updated = [...s.disclosures];
                            updated[index] = { ...updated[index], title: e.target.value };
                            s.setDisclosures(updated);
                          }}
                          className="form-input font-medium w-64 sm:w-96"
                          placeholder="Disclosure title"
                        />
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={disclosure.enabled}
                          onChange={(e) => {
                            const updated = [...s.disclosures];
                            updated[index] = { ...updated[index], enabled: e.target.checked };
                            s.setDisclosures(updated);
                          }}
                          className="sr-only peer"
                        />
                        <div className="toggle-switch"></div>
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          s.setDisclosures(s.disclosures.filter((_, i) => i !== index));
                        }}
                        className="p-1.5 text-muted hover:text-danger transition-colors"
                        title="Remove disclosure"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                      </button>
                    </div>
                  </div>

                  <MarkdownEditor
                    value={disclosure.content}
                    onChange={(value) => {
                      const updated = [...s.disclosures];
                      updated[index] = { ...updated[index], content: value };
                      s.setDisclosures(updated);
                    }}
                    placeholder="Enter compliance disclosure content in Markdown..."
                    rows={15}
                  />
                </div>
              ))}

              <button
                type="button"
                onClick={() => {
                  const newKey = `custom_${Date.now()}`;
                  s.setDisclosures([
                    ...s.disclosures,
                    { key: newKey, title: '', enabled: false, content: '' },
                  ]);
                }}
                className="btn-secondary w-full"
              >
                + Add Disclosure
              </button>
            </div>
          )}

          {/* Save Button */}
          <div className="mt-6 pt-6 border-t border-primary flex justify-end">
            <button
              onClick={s.handleSave}
              disabled={s.isSaving}
              className={`btn-primary${s.isSaving ? 'btn-disabled' : ''}`}
            >
              {s.isSaving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
