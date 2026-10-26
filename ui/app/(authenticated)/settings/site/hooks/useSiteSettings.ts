// ui/app/(authenticated)/settings/site/hooks/useSiteSettings.ts

'use client';

import { useEffect, useRef, useState } from 'react';
import { useRoleAccess } from '@/features/roles';
import { useUser } from '@/entities/user';
import { usePageVisibility } from '@/entities/page-visibility';
import { apiRequest } from '@/shared/api';
import { useToast } from '@/features/toast';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import { LIMITS } from '@/shared/lib/constants';
import type {
  Testimonial,
  FeatureBlock,
  HeroConfig,
  SiteContent,
  TabId,
  PageVisibility,
  DisclosureBlock,
  ComplianceSettings,
} from '../types';
import { SITE_TABS } from '../types';

interface SaveRequest {
  endpoint: string;
  body: unknown;
}

const DEFAULT_TWILIO_SMS_DISCLOSURE = `By providing your phone number and opting in to receive SMS messages from us, you consent to receive recurring automated text messages related to your account, including but not limited to: account notifications, alerts, and informational messages.

### Message Frequency
Message frequency varies based on your account activity and notification preferences.

### Message & Data Rates
Message and data rates may apply. Please check with your wireless carrier for details about your text plan.

### Opt-Out
You can opt out of receiving SMS messages at any time by replying **STOP** to any message you receive from us. After opting out, you will receive a final confirmation message and will no longer receive SMS messages from us unless you opt in again.

### Opt Back In
To opt back in, text **START** to the number you previously received messages from, or update your notification preferences in your account settings.

### Help
For help, reply **HELP** to any message, or contact us through our contact page.

### Privacy
Your phone number and messaging data will be handled in accordance with our [Privacy Policy](/privacy). We do not sell or share your phone number or opt-in data with third parties for marketing purposes.

### Supported Carriers
Major US carriers are supported. Carriers are not liable for delayed or undelivered messages.`;

const DEFAULT_COMPLIANCE: ComplianceSettings = {
  rosca_enabled: false,
  trial_disclosure:
    'After your {trial_days}-day free trial ends on {trial_end_date}, ' +
    'you will be automatically charged {price} every {interval} until you cancel.',
  recurring_disclosure:
    'You will be charged {price} today and automatically every {interval} until you cancel.',
  one_time_disclosure: 'This is a one-time payment of {price}. No recurring charges.',
  cancellation_instructions:
    'You can cancel anytime from your account Settings → Billing page. ' +
    'Your access continues until the end of your billing period.',
  consent_checkbox_text:
    'I understand this is a recurring subscription and I will be charged ' +
    '{price} every {interval} until I cancel.',
  registration_disclosure:
    'By creating an account with the {plan_name} plan, you agree to be charged ' +
    '{price}/{interval} after any applicable trial period. ' +
    'You can cancel anytime from your account settings.',
};

const DEFAULT_DISCLOSURES: DisclosureBlock[] = [
  {
    key: 'sms-consent',
    title: 'SMS / Messaging Consent',
    enabled: true,
    content: DEFAULT_TWILIO_SMS_DISCLOSURE,
  },
];

const REMOVE_MESSAGE = 'Removed when you save. This cannot be undone after saving.';

const DEFAULT_HERO: HeroConfig = {
  visible: true,
  headline: null,
  subtext: null,
  cta_text: null,
  cta_link: null,
};

const DEFAULT_PAGE_VISIBILITY: PageVisibility = {
  about: true,
  compliance: true,
  contact: true,
  docs: true,
  privacy: true,
  support: true,
  terms: true,
};

export function useSiteSettings() {
  const { hasAccess, isLoading: accessLoading } = useRoleAccess(['super_admin']);
  const { user } = useUser();
  const { toast } = useToast();
  const confirm = useConfirm();
  const { refetch: refetchPageVisibility } = usePageVisibility();

  const [activeTab, setActiveTab] = useState<TabId>('visibility');
  const [siteContent, setSiteContent] = useState<SiteContent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Form states
  const [heroConfig, setHeroConfig] = useState<HeroConfig>(DEFAULT_HERO);
  const [allowRegistration, setAllowRegistration] = useState(false);
  const [testimonials, setTestimonials] = useState<Testimonial[]>([]);
  const [features, setFeatures] = useState<FeatureBlock[]>([]);
  const [termsContent, setTermsContent] = useState('');
  const [termsLastUpdated, setTermsLastUpdated] = useState('');
  const [privacyContent, setPrivacyContent] = useState('');
  const [privacyLastUpdated, setPrivacyLastUpdated] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactAddress, setContactAddress] = useState('');
  const [aboutTitle, setAboutTitle] = useState('');
  const [aboutSubtitle, setAboutSubtitle] = useState('');
  const [aboutStory, setAboutStory] = useState('');
  const [pageVisibility, setPageVisibility] = useState<PageVisibility>(DEFAULT_PAGE_VISIBILITY);
  const [complianceSettings, setComplianceSettings] = useState<ComplianceSettings>(DEFAULT_COMPLIANCE);
  const [disclosures, setDisclosures] = useState<DisclosureBlock[]>(DEFAULT_DISCLOSURES);

  // Fetch all site content
  useEffect(() => {
    const fetchContent = async () => {
      if (!hasAccess) return;

      try {
        const data = await apiRequest<{ items: SiteContent[] }>('/site-content/');
        setSiteContent(data.items || []);

        data.items?.forEach((item: SiteContent) => {
          switch (item.page_id) {
            case 'home':
              if (item.content.hero) {
                setHeroConfig(prev => ({ ...prev, ...item.content.hero }));
              }
              if (item.content.testimonials) {
                setTestimonials(item.content.testimonials);
              }
              if (item.content.features) {
                const sortedFeatures = [...item.content.features].sort(
                  (a: FeatureBlock, b: FeatureBlock) => a.sort_order - b.sort_order
                );
                setFeatures(sortedFeatures);
              }
              break;
            case 'terms':
              setTermsContent(item.content.content || '');
              setTermsLastUpdated(item.content.last_updated || '');
              break;
            case 'privacy':
              setPrivacyContent(item.content.content || '');
              setPrivacyLastUpdated(item.content.last_updated || '');
              break;
            case 'contact':
              setContactEmail(item.content.email || '');
              setContactPhone(item.content.phone || '');
              setContactAddress(item.content.address || '');
              break;
            case 'about':
              setAboutTitle(item.content.title || '');
              setAboutSubtitle(item.content.subtitle || '');
              setAboutStory(item.content.story || '');
              break;
            case 'settings':
              if (item.content.page_visibility) {
                setPageVisibility(prev => ({
                  ...prev,
                  ...item.content.page_visibility,
                }));
              }
              if (item.content.site_settings) {
                setAllowRegistration(item.content.site_settings.allow_registration !== false);
              }
              if (item.content.compliance) {
                setComplianceSettings(prev => ({
                  ...prev,
                  ...item.content.compliance,
                }));
              }
              if (item.content.disclosures && Array.isArray(item.content.disclosures)) {
                setDisclosures(prev => {
                  const savedMap = new Map(
                    item.content.disclosures.map((d: DisclosureBlock) => [d.key, d])
                  );
                  const merged = prev.map(defaultBlock => {
                    const saved = savedMap.get(defaultBlock.key);
                    return saved ? { ...defaultBlock, ...saved } : defaultBlock;
                  });
                  const defaultKeys = new Set(prev.map(d => d.key));
                  const extras = item.content.disclosures.filter(
                    (d: DisclosureBlock) => !defaultKeys.has(d.key)
                  );
                  return [...merged, ...extras];
                });
              }
              break;
          }
        });
      } catch (err) {
        console.error('Failed to fetch site content:', err);
        toast({ title: 'Failed to load site content', variant: 'destructive' });
      } finally {
        setIsLoading(false);
      }
    };

    fetchContent();
  }, [hasAccess, toast]);

  const buildRequests = (tab: TabId): SaveRequest[] => {
    switch (tab) {
      case 'visibility':
        return [
          { endpoint: '/site-content/settings/page-visibility', body: pageVisibility },
          { endpoint: '/site-content/settings/registration', body: { allow_registration: allowRegistration } },
        ];
      case 'hero':
        return [{ endpoint: '/site-content/home/hero', body: heroConfig }];
      case 'testimonials':
        return [{ endpoint: '/site-content/home/testimonials', body: { testimonials } }];
      case 'features':
        return [{ endpoint: '/site-content/home/features', body: { features } }];
      case 'terms':
        return [{ endpoint: '/site-content/terms', body: { content: termsContent, last_updated: termsLastUpdated || undefined } }];
      case 'privacy':
        return [{ endpoint: '/site-content/privacy', body: { content: privacyContent, last_updated: privacyLastUpdated || undefined } }];
      case 'contact':
        return [{
          endpoint: '/site-content/contact',
          body: { email: contactEmail || null, phone: contactPhone || null, address: contactAddress || null },
        }];
      case 'about':
        return [{ endpoint: '/site-content/about/story', body: { title: aboutTitle || null, subtitle: aboutSubtitle || null, story: aboutStory } }];
      case 'compliance':
        return [{ endpoint: '/site-content/settings/compliance', body: complianceSettings }];
      case 'disclosures':
        return [{ endpoint: '/site-content/settings/disclosures', body: { disclosures } }];
    }
  };

  // Serialized requests per tab as last loaded or saved
  const savedRef = useRef<Partial<Record<TabId, string>>>({});
  const baselineSetRef = useRef(false);
  const snapshot = (tab: TabId) => JSON.stringify(buildRequests(tab));

  // Records the loaded content as the clean state once loading finishes
  useEffect(() => {
    if (isLoading || baselineSetRef.current) return;
    baselineSetRef.current = true;
    SITE_TABS.forEach(({ id }) => {
      savedRef.current[id] = snapshot(id);
    });
  });

  const handleSave = async () => {
    const dirty = SITE_TABS.filter(({ id }) => snapshot(id) !== savedRef.current[id]);
    if (dirty.length === 0) {
      toast({ title: 'No changes to save', variant: 'info' });
      return;
    }

    setIsSaving(true);
    let visibilitySaved = false;
    try {
      for (const tab of dirty) {
        const snap = snapshot(tab.id);
        try {
          for (const request of buildRequests(tab.id)) {
            await apiRequest(request.endpoint, { method: 'PUT', body: JSON.stringify(request.body) });
          }
        } catch (err: unknown) {
          console.error('Save error:', err);
          toast({
            title: `Failed to save ${tab.label}`,
            description: err instanceof Error ? err.message : String(err),
            variant: 'destructive',
          });
          return;
        }
        savedRef.current[tab.id] = snap;
        if (tab.id === 'visibility') visibilitySaved = true;
      }
      toast({ title: `Saved ${dirty.length} section${dirty.length === 1 ? '' : 's'}`, variant: 'success' });
    } finally {
      if (visibilitySaved) await refetchPageVisibility();
      setIsSaving(false);
    }
  };

  // Testimonial management
  const addTestimonial = () => {
    if (testimonials.length >= LIMITS.MAX_TESTIMONIALS) {
      toast({ title: `Maximum of ${LIMITS.MAX_TESTIMONIALS} testimonials allowed`, variant: 'destructive' });
      return;
    }
    setTestimonials([...testimonials, { name: '', title: '', feedback: '' }]);
  };

  const confirmRemove = (title: string) =>
    confirm({ title, message: REMOVE_MESSAGE, confirmLabel: 'Remove', variant: 'warning' });

  const removeTestimonial = async (index: number) => {
    if (!(await confirmRemove('Remove testimonial?'))) return;
    setTestimonials(prev => prev.filter((_, i) => i !== index));
  };

  const updateTestimonial = (index: number, field: keyof Testimonial, value: string) => {
    const updated = [...testimonials];
    updated[index] = { ...updated[index], [field]: value };
    setTestimonials(updated);
  };

  // Feature block management
  const addFeature = () => {
    const newId = Date.now().toString();
    const newSortOrder = features.length;
    setFeatures([
      ...features,
      {
        id: newId,
        title: '',
        description: '',
        thumbnail: '',
        media_type: 'image',
        workflow_id: null,
        sort_order: newSortOrder,
        icon: 'sparkles',
        visible: true,
      },
    ]);
  };

  const removeFeature = async (index: number) => {
    if (!(await confirmRemove('Remove feature block?'))) return;
    setFeatures(prev => prev.filter((_, i) => i !== index).map((f, i) => ({ ...f, sort_order: i })));
  };

  const removeDisclosure = async (index: number) => {
    if (!(await confirmRemove('Remove disclosure?'))) return;
    setDisclosures(prev => prev.filter((_, i) => i !== index));
  };

  const updateFeature = (index: number, field: keyof FeatureBlock, value: any) => {
    setFeatures(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const moveFeature = (index: number, direction: 'up' | 'down') => {
    if (
      (direction === 'up' && index === 0) ||
      (direction === 'down' && index === features.length - 1)
    ) {
      return;
    }
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    const updated = [...features];
    [updated[index], updated[newIndex]] = [updated[newIndex], updated[index]];
    setFeatures(updated.map((f, i) => ({ ...f, sort_order: i })));
  };

  return {
    // Access
    hasAccess,
    accessLoading,
    user,
    // Loading
    isLoading,
    isSaving,
    // Tab
    activeTab,
    setActiveTab,
    // Hero
    heroConfig,
    setHeroConfig,
    // Registration
    allowRegistration,
    setAllowRegistration,
    // Testimonials
    testimonials,
    addTestimonial,
    removeTestimonial,
    updateTestimonial,
    // Features
    features,
    addFeature,
    removeFeature,
    updateFeature,
    moveFeature,
    // Terms
    termsContent,
    setTermsContent,
    termsLastUpdated,
    setTermsLastUpdated,
    // Privacy
    privacyContent,
    setPrivacyContent,
    privacyLastUpdated,
    setPrivacyLastUpdated,
    // Contact
    contactEmail,
    setContactEmail,
    contactPhone,
    setContactPhone,
    contactAddress,
    setContactAddress,
    // About
    aboutTitle,
    setAboutTitle,
    aboutSubtitle,
    setAboutSubtitle,
    aboutStory,
    setAboutStory,
    // Page visibility
    pageVisibility,
    setPageVisibility,
    // Compliance
    complianceSettings,
    setComplianceSettings,
    // Disclosures
    disclosures,
    setDisclosures,
    removeDisclosure,
    // Save
    handleSave,
  };
}
