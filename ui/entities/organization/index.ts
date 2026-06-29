// ui/entities/organization/index.ts

// Organization entity - branding and settings contexts

// Branding
export {
  BrandingProvider,
  useBranding,
  type BrandingConfig
} from './branding';

// Organization settings
export {
  OrgSettingsProvider,
  useOrgSettings,
  type CardSize
} from './settings';
