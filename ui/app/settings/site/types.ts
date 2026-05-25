// ui/app/settings/site/types.ts

export interface Testimonial {
  name: string;
  title: string;
  feedback: string;
  avatar_url?: string;
}

export interface FeatureBlock {
  id: string;
  title: string;
  description: string;
  thumbnail: string;
  media_type: 'image' | 'video';
  workflow_id?: string | null;
  sort_order: number;
  icon?: string | null;
  visible?: boolean;
}

export interface HeroConfig {
  visible: boolean;
  headline: string | null;
  subtext: string | null;
  cta_text: string | null;
  cta_link: string | null;
}

export interface SiteContent {
  id: string;
  page_id: string;
  content: Record<string, any>;
  updated_at: string;
}

export type TabId = 'visibility' | 'hero' | 'testimonials' | 'features' | 'terms' | 'privacy' | 'contact' | 'about' | 'compliance' | 'disclosures';

export interface PageVisibility {
  about: boolean;
  blueprints: boolean;
  compliance: boolean;
  contact: boolean;
  docs: boolean;
  privacy: boolean;
  support: boolean;
  terms: boolean;
}

export interface DisclosureBlock {
  key: string;
  title: string;
  enabled: boolean;
  content: string;
}

export interface ComplianceSettings {
  rosca_enabled: boolean;
  trial_disclosure: string;
  recurring_disclosure: string;
  one_time_disclosure: string;
  cancellation_instructions: string;
  consent_checkbox_text: string;
  registration_disclosure: string;
}
