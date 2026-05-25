// ui/widgets/layout/BrandingSettingsForm.tsx

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useUser } from '@/entities/user';
import { useBranding } from '@/entities/organization';
import { getOrganization, updateOrganization, publicApiRequest } from '@/shared/api';
import { TIMEOUTS } from '@/shared/lib/constants';
import { Palette, Image as ImageIcon, Sparkles, Globe } from 'lucide-react';

interface BrandingSettingsFormProps {
  orgId?: string;  // If provided, edit that org. If not, auto-detect based on role.
  showCustomDomain?: boolean;  // Whether to show the custom domain section
  onSaveSuccess?: () => void;  // Optional callback after successful save
  readOnly?: boolean;  // If true, show form in read-only mode (for super-admin viewing other orgs)
}

export default function BrandingSettingsForm({
  orgId: propOrgId,
  showCustomDomain = false,
  onSaveSuccess,
  readOnly = false
}: BrandingSettingsFormProps) {
  const router = useRouter();
  const userContext = useUser();
  const { branding, refreshBranding } = useBranding();

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [targetOrgId, setTargetOrgId] = useState<string | null>(propOrgId || null);
  const [organization, setOrganization] = useState<any>(null);

  const [formData, setFormData] = useState({
    // Note: companyName, shortName, and tagline are now managed on Organization Details page
    shortName: '',  // Still needed for header preview
    primaryColor: '#3B82F6',
    secondaryColor: '#10B981',
    accentColor: '#F59E0B',
    logoUrl: '',
    heroGradientStart: '#2563EB',
    heroGradientEnd: '#4F46E5',
    headerBackground: '#FFFFFF',
    headerText: '#3B82F6',
    sectionBackground: '#F9FAFB',
    customDomain: ''
  });

  // Load organization and branding data
  useEffect(() => {
    const loadOrganizationData = async () => {
      if (!userContext?.user) return;

      try {
        setIsLoading(true);

        const isSuperAdmin = userContext.user.role === 'super_admin';

        // Determine which org to load
        let orgIdToLoad = propOrgId;

        if (!orgIdToLoad) {
          // Auto-detect: super_admin loads system org, others load their own org
          if (isSuperAdmin) {
            try {
              const brandingData = await publicApiRequest<{ organization_id: string }>('/public/branding');
              orgIdToLoad = brandingData.organization_id;
            } catch {
              // Branding not configured yet
            }
          } else {
            orgIdToLoad = userContext.user.org_id;
          }
        }

        if (!orgIdToLoad) {
          setErrorMessage('Could not determine organization');
          return;
        }

        setTargetOrgId(orgIdToLoad);
        const org = await getOrganization(orgIdToLoad);
        setOrganization(org);

        // Load existing branding if available
        const orgBranding = org.settings?.branding;
        const customDomain = org.settings?.domain?.custom_domain || '';

        if (orgBranding) {
          setFormData({
            shortName: orgBranding.short_name || '',  // For header preview
            primaryColor: orgBranding.primary_color || '#3B82F6',
            secondaryColor: orgBranding.secondary_color || '#10B981',
            accentColor: orgBranding.accent_color || '#F59E0B',
            logoUrl: orgBranding.logo_url || '',
            heroGradientStart: orgBranding.hero_gradient_start || '#2563EB',
            heroGradientEnd: orgBranding.hero_gradient_end || '#4F46E5',
            headerBackground: orgBranding.header_background || '#FFFFFF',
            headerText: orgBranding.header_text || '#3B82F6',
            sectionBackground: orgBranding.section_background || '#F9FAFB',
            customDomain
          });
        } else {
          // Use context branding as fallback
          setFormData({
            shortName: branding.shortName || '',  // For header preview
            primaryColor: branding.primaryColor,
            secondaryColor: branding.secondaryColor,
            accentColor: branding.accentColor,
            logoUrl: branding.logoUrl || '',
            heroGradientStart: branding.heroGradientStart || '#2563EB',
            heroGradientEnd: branding.heroGradientEnd || '#4F46E5',
            headerBackground: branding.headerBackground || '#FFFFFF',
            headerText: branding.headerText || '#3B82F6',
            sectionBackground: branding.sectionBackground || '#F9FAFB',
            customDomain
          });
        }
      } catch (error) {
        console.error('Error loading organization:', error);
        setErrorMessage('Failed to load organization');
      } finally {
        setIsLoading(false);
      }
    };

    loadOrganizationData();
  }, [userContext?.user, propOrgId, branding]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setSaveStatus('idle');
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!targetOrgId) {
      setErrorMessage('No organization found');
      setSaveStatus('error');
      return;
    }

    setIsSaving(true);
    setSaveStatus('idle');
    setErrorMessage('');

    try {
      const org = await getOrganization(targetOrgId);

      const updatedSettings = {
        ...org.settings,
        branding: {
          // Preserve company_name, short_name, tagline - they're now managed on Org Details page
          ...org.settings?.branding,
          primary_color: formData.primaryColor,
          secondary_color: formData.secondaryColor,
          accent_color: formData.accentColor,
          logo_url: formData.logoUrl || null,
          hero_gradient_start: formData.heroGradientStart,
          hero_gradient_end: formData.heroGradientEnd,
          header_background: formData.headerBackground,
          header_text: formData.headerText,
          section_background: formData.sectionBackground
        },
        ...(showCustomDomain && {
          domain: {
            ...org.settings?.domain,
            custom_domain: formData.customDomain || null
          }
        })
      };

      await updateOrganization(targetOrgId, { settings: updatedSettings });

      setSaveStatus('success');
      await refreshBranding();

      if (onSaveSuccess) {
        onSaveSuccess();
      }

      setTimeout(() => setSaveStatus('idle'), TIMEOUTS.MESSAGE_DISMISS);
    } catch (error) {
      console.error('Error saving branding:', error);
      setErrorMessage(error instanceof Error ? error.message : 'Failed to save branding settings');
      setSaveStatus('error');
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = () => {
    setFormData(prev => ({
      shortName: prev.shortName,  // Preserve current shortName (read-only here)
      primaryColor: '#3B82F6',
      secondaryColor: '#10B981',
      accentColor: '#F59E0B',
      logoUrl: '',
      heroGradientStart: '#2563EB',
      heroGradientEnd: '#4F46E5',
      headerBackground: '#FFFFFF',
      headerText: '#3B82F6',
      sectionBackground: '#F9FAFB',
      customDomain: ''
    }));
    setSaveStatus('idle');
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted">Loading...</div>
      </div>
    );
  }

  // Determine if we're editing the system org (for header display)
  const isSuperAdmin = userContext?.user?.role === 'super_admin';
  const isEditingSystemOrg = isSuperAdmin && !propOrgId;

  return (
    <>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold text-primary">
            {isEditingSystemOrg ? 'System Branding' : 'Branding Settings'}
          </h1>
          {isEditingSystemOrg && (
            <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-info-subtle text-info">
              Site-wide
            </span>
          )}
        </div>
        <p className="text-secondary">
          {isEditingSystemOrg
            ? 'These settings apply to all public pages (homepage, pricing, footer, etc.) and serve as the default branding for all organizations.'
            : organization
              ? `Customize branding for ${organization.name}`
              : 'Customize your organization\'s branding, including company name, colors, and logo.'}
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-8">

      {/* Brand Colors */}
      <div className="bg-card rounded-lg shadow-md p-4 sm:p-6 border border-primary overflow-hidden">
        <div className="flex items-center mb-6">
          <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900 rounded-lg flex items-center justify-center mr-3">
            <Palette className="w-5 h-5 text-purple-600 dark:text-purple-400" />
          </div>
          <h2 className="text-xl font-bold text-primary">
            Brand Colors
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex flex-col p-3 bg-card /50 rounded-lg">
            <label htmlFor="primaryColor" className="text-sm font-medium text-secondary mb-2">
              Primary
            </label>
            <div className="flex items-center gap-2 mb-1">
              <input
                type="color"
                id="primaryColor"
                name="primaryColor"
                value={formData.primaryColor}
                onChange={handleChange}
                disabled={readOnly}
                className="h-8 w-8 flex-shrink-0 rounded border border-primary cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
              />
              <input
                type="text"
                value={formData.primaryColor}
                onChange={(e) => setFormData(prev => ({ ...prev, primaryColor: e.target.value }))}
                disabled={readOnly}
                className="w-20 px-1 py-1 rounded-md border border-primary bg-card text-primary font-mono text-xs disabled:cursor-not-allowed disabled:opacity-60"
                placeholder="#3B82F6"
              />
            </div>
            <p className="text-muted text-xs">
              Main brand color for buttons and links
            </p>
          </div>

          <div className="flex flex-col p-3 bg-card /50 rounded-lg">
            <label htmlFor="secondaryColor" className="text-sm font-medium text-secondary mb-2">
              Secondary
            </label>
            <div className="flex items-center gap-2 mb-1">
              <input
                type="color"
                id="secondaryColor"
                name="secondaryColor"
                value={formData.secondaryColor}
                onChange={handleChange}
                disabled={readOnly}
                className="h-8 w-8 flex-shrink-0 rounded border border-primary cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
              />
              <input
                type="text"
                value={formData.secondaryColor}
                onChange={(e) => setFormData(prev => ({ ...prev, secondaryColor: e.target.value }))}
                disabled={readOnly}
                className="w-20 px-1 py-1 rounded-md border border-primary bg-card text-primary font-mono text-xs disabled:cursor-not-allowed disabled:opacity-60"
                placeholder="#10B981"
              />
            </div>
            <p className="text-muted text-xs">
              Success states and highlights
            </p>
          </div>

          <div className="flex flex-col p-3 bg-card /50 rounded-lg">
            <label htmlFor="accentColor" className="text-sm font-medium text-secondary mb-2">
              Accent
            </label>
            <div className="flex items-center gap-2 mb-1">
              <input
                type="color"
                id="accentColor"
                name="accentColor"
                value={formData.accentColor}
                onChange={handleChange}
                disabled={readOnly}
                className="h-8 w-8 flex-shrink-0 rounded border border-primary cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
              />
              <input
                type="text"
                value={formData.accentColor}
                onChange={(e) => setFormData(prev => ({ ...prev, accentColor: e.target.value }))}
                disabled={readOnly}
                className="w-20 px-1 py-1 rounded-md border border-primary bg-card text-primary font-mono text-xs disabled:cursor-not-allowed disabled:opacity-60"
                placeholder="#F59E0B"
              />
            </div>
            <p className="text-muted text-xs">
              Warnings and special emphasis
            </p>
          </div>
        </div>

        {/* Color Preview */}
        <div className="mt-6 p-4 bg-card rounded-lg">
          <p className="text-sm font-medium text-secondary mb-3">Preview:</p>
          <div className="flex gap-3">
            <button
              type="button"
              style={{ backgroundColor: formData.primaryColor }}
              className="px-4 py-2 rounded text-white font-medium"
            >
              Primary Button
            </button>
            <button
              type="button"
              style={{ backgroundColor: formData.secondaryColor }}
              className="px-4 py-2 rounded text-white font-medium"
            >
              Secondary
            </button>
            <button
              type="button"
              style={{ backgroundColor: formData.accentColor }}
              className="px-4 py-2 rounded text-white font-medium"
            >
              Accent
            </button>
          </div>
        </div>
      </div>

      {/* Marketing Page Colors */}
      <div className="bg-card rounded-lg shadow-md p-4 sm:p-6 border border-primary overflow-hidden">
        <div className="flex items-center mb-6">
          <div className="w-10 h-10 bg-indigo-100 dark:bg-indigo-900 rounded-lg flex items-center justify-center mr-3">
            <Palette className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <h2 className="text-xl font-bold text-primary">
            Marketing Page Colors
          </h2>
        </div>

        <p className="text-sm text-secondary mb-6">
          Customize colors for your public-facing marketing pages (homepage, pricing, etc.)
        </p>

        <div className="space-y-6">
          {/* Hero Gradient */}
          <div>
            <h3 className="text-md font-semibold text-primary mb-4">Hero Section Gradient</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="heroGradientStart" className="block text-sm font-medium text-secondary mb-2">
                  Gradient Start
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    id="heroGradientStart"
                    name="heroGradientStart"
                    value={formData.heroGradientStart}
                    onChange={handleChange}
                    disabled={readOnly}
                    className="h-10 w-10 flex-shrink-0 rounded border border-primary cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <input
                    type="text"
                    value={formData.heroGradientStart}
                    onChange={(e) => setFormData(prev => ({ ...prev, heroGradientStart: e.target.value }))}
                    disabled={readOnly}
                    className="w-24 px-2 py-2 rounded-md border border-primary bg-card text-primary font-mono text-sm disabled:cursor-not-allowed disabled:opacity-60"
                    placeholder="#2563EB"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="heroGradientEnd" className="block text-sm font-medium text-secondary mb-2">
                  Gradient End
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    id="heroGradientEnd"
                    name="heroGradientEnd"
                    value={formData.heroGradientEnd}
                    onChange={handleChange}
                    disabled={readOnly}
                    className="h-10 w-10 flex-shrink-0 rounded border border-primary cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <input
                    type="text"
                    value={formData.heroGradientEnd}
                    onChange={(e) => setFormData(prev => ({ ...prev, heroGradientEnd: e.target.value }))}
                    disabled={readOnly}
                    className="w-24 px-2 py-2 rounded-md border border-primary bg-card text-primary font-mono text-sm disabled:cursor-not-allowed disabled:opacity-60"
                    placeholder="#4F46E5"
                  />
                </div>
              </div>
            </div>

            {/* Hero Gradient Preview */}
            <div className="mt-4 p-8 rounded-lg text-center" style={{
              background: `linear-gradient(135deg, ${formData.heroGradientStart} 0%, ${formData.heroGradientEnd} 100%)`
            }}>
              <h3 className="text-2xl font-bold text-white mb-2">Hero Section Preview</h3>
              <p className="text-white/90">This is how your hero gradient will look</p>
            </div>
          </div>

          {/* Header Colors */}
          <div>
            <h3 className="text-md font-semibold text-primary mb-4">Header/Navigation Bar</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="headerBackground" className="block text-sm font-medium text-secondary mb-2">
                  Background Color
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    id="headerBackground"
                    name="headerBackground"
                    value={formData.headerBackground}
                    onChange={handleChange}
                    disabled={readOnly}
                    className="h-10 w-10 flex-shrink-0 rounded border border-primary cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <input
                    type="text"
                    value={formData.headerBackground}
                    onChange={(e) => setFormData(prev => ({ ...prev, headerBackground: e.target.value }))}
                    disabled={readOnly}
                    className="w-24 px-2 py-2 rounded-md border border-primary bg-card text-primary font-mono text-sm disabled:cursor-not-allowed disabled:opacity-60"
                    placeholder="#FFFFFF"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="headerText" className="block text-sm font-medium text-secondary mb-2">
                  Text/Logo Color
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    id="headerText"
                    name="headerText"
                    value={formData.headerText}
                    onChange={handleChange}
                    disabled={readOnly}
                    className="h-10 w-10 flex-shrink-0 rounded border border-primary cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <input
                    type="text"
                    value={formData.headerText}
                    onChange={(e) => setFormData(prev => ({ ...prev, headerText: e.target.value }))}
                    disabled={readOnly}
                    className="w-24 px-2 py-2 rounded-md border border-primary bg-card text-primary font-mono text-sm disabled:cursor-not-allowed disabled:opacity-60"
                    placeholder="#3B82F6"
                  />
                </div>
              </div>
            </div>

            {/* Header Preview */}
            <div className="mt-4 rounded-lg border border-primary overflow-hidden">
              <div className="p-4 flex items-center justify-between" style={{
                backgroundColor: formData.headerBackground
              }}>
                <div className="flex items-center">
                  {formData.logoUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element -- dynamic logo URL
                    <img
                      src={formData.logoUrl}
                      alt="Logo"
                      className="w-8 h-8 rounded object-contain"
                    />
                  ) : formData.shortName ? (
                    <span className="font-bold text-lg" style={{ color: formData.headerText }}>
                      {formData.shortName}
                    </span>
                  ) : null}
                </div>
                <div className="flex gap-4">
                  <span style={{ color: formData.headerText }}>Features</span>
                  <span style={{ color: formData.headerText }}>Pricing</span>
                  <span style={{ color: formData.headerText }}>About</span>
                </div>
              </div>
            </div>
          </div>

          {/* Section Background */}
          <div>
            <h3 className="text-md font-semibold text-primary mb-4">Section Background</h3>
            <div>
              <label htmlFor="sectionBackground" className="block text-sm font-medium text-secondary mb-2">
                Alternating Section Color
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  id="sectionBackground"
                  name="sectionBackground"
                  value={formData.sectionBackground}
                  onChange={handleChange}
                  disabled={readOnly}
                  className="h-10 w-10 flex-shrink-0 rounded border border-primary cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
                />
                <input
                  type="text"
                  value={formData.sectionBackground}
                  onChange={(e) => setFormData(prev => ({ ...prev, sectionBackground: e.target.value }))}
                  disabled={readOnly}
                  className="w-24 px-2 py-2 rounded-md border border-primary bg-card text-primary font-mono text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  placeholder="#F9FAFB"
                />
              </div>
              <p className="text-sm text-secondary mt-2">
                Used for alternating sections on marketing pages
              </p>
            </div>

            {/* Section Preview */}
            <div className="mt-4 rounded-lg overflow-hidden border border-primary">
              <div className="p-6 bg-card">
                <h4 className="font-semibold text-primary mb-2">Main Section</h4>
                <p className="text-sm text-secondary">Content on white background</p>
              </div>
              <div className="p-6" style={{ backgroundColor: formData.sectionBackground }}>
                <h4 className="font-semibold text-primary mb-2">Alternating Section</h4>
                <p className="text-sm text-secondary">Content with custom section background</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Custom Domain Configuration - only show if enabled */}
      {showCustomDomain && (
        <div className="bg-card rounded-lg shadow-md p-6 border border-primary">
          <div className="flex items-center mb-6">
            <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900 rounded-lg flex items-center justify-center mr-3">
              <Globe className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <h2 className="text-xl font-bold text-primary">
              Custom Domain
            </h2>
          </div>

          <div>
            <label htmlFor="custom-domain" className="block text-sm font-medium text-secondary mb-2">
              Custom Domain Name
            </label>
            <input
              id="custom-domain"
              type="text"
              value={formData.customDomain}
              onChange={(e) => setFormData({ ...formData, customDomain: e.target.value })}
              disabled={readOnly}
              className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
              placeholder="workflows.mycompany.com"
            />
            <p className="text-sm text-secondary mt-1">
              Set a custom domain for your branded landing page. Leave empty to use the default domain.
            </p>

            <div className="mt-4 p-4 bg-info-subtle border border-info rounded-lg">
              <h4 className="text-sm font-semibold text-info mb-2 flex items-center">
                <Sparkles className="w-4 h-4 mr-2" />
                Custom Domain Setup Instructions
              </h4>
              <ol className="text-sm text-info space-y-2 list-decimal list-inside">
                <li>Configure Cloudflare tunnel credentials in environment variables (see documentation)</li>
                <li>Add your custom domain in the field above (e.g., workflows.mycompany.com)</li>
                <li>Configure DNS CNAME record pointing to your tunnel</li>
                <li>Save changes and test by visiting your custom domain</li>
              </ol>
            </div>
          </div>
        </div>
      )}

      {/* Logo */}
      <div className="bg-card rounded-lg shadow-md p-6 border border-primary">
        <div className="flex items-center mb-6">
          <div className="w-10 h-10 bg-success-subtle rounded-lg flex items-center justify-center mr-3">
            <ImageIcon className="w-5 h-5 text-success" />
          </div>
          <h2 className="text-xl font-bold text-primary">
            Logo
          </h2>
        </div>

        <div>
          <label htmlFor="logoUrl" className="block text-sm font-medium text-secondary mb-2">
            Logo URL (optional)
          </label>
          <input
            type="text"
            id="logoUrl"
            name="logoUrl"
            value={formData.logoUrl}
            onChange={handleChange}
            disabled={readOnly}
            className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
            placeholder="/uploads/logo.png"
          />
          <p className="text-sm text-secondary mt-1">
            URL to your logo image. Leave empty to use company name as text logo.
          </p>
          <div className="mt-4 p-4 bg-info-subtle border border-info rounded-lg">
            <p className="text-sm text-info flex items-center">
              <Sparkles className="w-4 h-4 mr-2" />
              File upload coming soon! For now, upload your logo to /public/uploads/ and enter the path here.
            </p>
          </div>
        </div>
      </div>

      {/* Status Messages */}
      {saveStatus === 'success' && (
        <div className="bg-success-subtle border border-success text-success px-4 py-3 rounded-md">
          Branding settings saved successfully! Changes are applied immediately.
        </div>
      )}

      {saveStatus === 'error' && (
        <div className="alert alert-error">
          Error: {errorMessage || 'Failed to save branding settings. Please try again.'}
        </div>
      )}

      {/* Action Buttons - hidden in read-only mode */}
      {!readOnly && (
        <div className="flex items-center justify-between pt-6 border-t border-primary">
          <button
            type="button"
            onClick={handleReset}
            className="px-6 py-2 border border-primary text-secondary rounded-md hover:bg-surface transition-colors"
          >
            Reset to Defaults
          </button>

          <button
            type="submit"
            disabled={isSaving}
            className="btn-primary px-6"
          >
            {isSaving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      )}
      </form>
    </>
  );
}
