// ui/shared/api/public.ts

/** Unauthenticated endpoints for public-facing pages - no auth headers, no token refresh. */

import { publicApiRequest } from './core';

export interface PublicSiteContent {
  id?: string;
  page: string;
  content: Record<string, unknown>;
}

export interface PublicBranding {
  org_name?: string;
  company_name?: string;
  short_name?: string;
  logo_url?: string | null;
  primary_color?: string;
  secondary_color?: string;
  accent_color?: string;
  tagline?: string;
  hero_gradient_start?: string;
  hero_gradient_end?: string;
  header_background?: string;
  header_text?: string;
  section_background?: string;
}

export interface PublicRegistrationSettings {
  allow_registration: boolean;
}

export interface PublicPageVisibility {
  about: boolean;
  blueprints: boolean;
  compliance: boolean;
  contact: boolean;
  docs: boolean;
  privacy: boolean;
  support: boolean;
  terms: boolean;
}

export interface PublicMaintenanceStatus {
  maintenance_mode: boolean;
  warning_mode: boolean;
  reason?: string | null;
  warning_until?: string | null;
}

export interface PublicContactInfo {
  email?: string;
  phone?: string;
  address?: string;
}

export interface PublicTeamMember {
  id: string;
  first_name: string;
  last_name: string;
  role: string;
  bio?: string;
}

export interface PublicComplianceSettings {
  rosca_enabled: boolean;
  trial_disclosure: string;
  recurring_disclosure: string;
  one_time_disclosure: string;
  cancellation_instructions: string;
  consent_checkbox_text: string;
  registration_disclosure: string;
}

export interface DocsManifest {
  version: string;
  updated_at: string;
  docs: Array<{
    id: string;
    title: string;
    description: string;
    icon: string;
    public: boolean;
  }>;
}

export async function getPublicSiteContent(page: string): Promise<PublicSiteContent> {
  return publicApiRequest<PublicSiteContent>(`/public/site-content/${page}`);
}

export async function getPublicBranding(): Promise<PublicBranding> {
  return publicApiRequest<PublicBranding>('/public/branding');
}

export async function getPublicRegistrationSettings(): Promise<PublicRegistrationSettings> {
  return publicApiRequest<PublicRegistrationSettings>('/public/registration-settings');
}

export async function getPublicPageVisibility(): Promise<PublicPageVisibility> {
  return publicApiRequest<PublicPageVisibility>('/public/page-visibility');
}

export async function getPublicMaintenanceStatus(): Promise<PublicMaintenanceStatus> {
  return publicApiRequest<PublicMaintenanceStatus>('/public/maintenance');
}

export async function getPublicContact(): Promise<PublicContactInfo> {
  return publicApiRequest<PublicContactInfo>('/public/contact');
}

export async function submitPublicContact(data: {
  name: string;
  email: string;
  company?: string;
  subject: string;
  message: string;
}): Promise<void> {
  return publicApiRequest<void>('/public/contact', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getPublicTeam(): Promise<PublicTeamMember[]> {
  return publicApiRequest<PublicTeamMember[]>('/public/team');
}

export async function getPublicComplianceSettings(): Promise<PublicComplianceSettings> {
  return publicApiRequest<PublicComplianceSettings>('/public/compliance-settings');
}

export async function getPublicDocsCatalog(): Promise<DocsManifest> {
  return publicApiRequest<DocsManifest>('/docs/catalog');
}

export async function getPublicPricingPlans(): Promise<Array<Record<string, unknown>>> {
  return publicApiRequest<Array<Record<string, unknown>>>('/pricing/plans');
}

export interface ProviderDocInfo {
  id: string;
  title: string;
  description: string;
  icon: string;
  public: boolean;
}

export interface ProviderDocsList {
  providers: ProviderDocInfo[];
}

export async function getProviderDocsList(): Promise<ProviderDocsList> {
  return publicApiRequest<ProviderDocsList>('/docs/providers');
}

export async function getProviderDocContent(slug: string): Promise<{ id: string; title: string; content: string }> {
  return publicApiRequest<{ id: string; title: string; content: string }>(`/docs/providers/${slug}`);
}

export async function getWorkflowDocContent(slug: string): Promise<{ id: string; title: string; content: string }> {
  return publicApiRequest<{ id: string; title: string; content: string }>(`/docs/workflows/${slug}`);
}
