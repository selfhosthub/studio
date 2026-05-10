// ui/shared/types/provider.ts

export type ProviderTier = 'basic' | 'advanced';

export type MarketplacePackageStatus = 'installed' | 'deactivated' | 'available';

export interface PackageVersion {
  version: string;
  download_url: string;
  release_date?: string;
  changelog?: string;
}

export interface MarketplacePackage {
  /** Package slug, e.g. "core" or "my-provider". */
  id: string;
  provider_id?: string;
  display_name: string;
  tier: ProviderTier;
  category: string;
  description: string;
  services_preview: string[];
  requires?: string[];
  credential_provider?: string;
  status: MarketplacePackageStatus;
  installed?: boolean;
  version?: string;
  /** Pinned-version download. */
  download_url?: string;
  /** Always-latest download. */
  latest_url?: string;
  /** Filesystem path for directory-based install. */
  path?: string;
  /** Available versions for rollback. */
  versions?: PackageVersion[];
  bug_report_url?: string;
  installed_version?: string;
}

export interface MarketplaceCatalog {
  version: string;
  packages: MarketplacePackage[];
  warnings?: string[];
}

export interface EntitlementTokenStatus {
  configured: boolean;
}
