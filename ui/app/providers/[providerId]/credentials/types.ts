// ui/app/providers/[providerId]/credentials/types.ts

/**
 * Shared types for the credential management page.
 */

/** Shape of the credential form fields */
export interface CredentialFormValues {
  name: string;
  credential_type: string;
  secret_data: string;
  expires_at: string;
}

/** Default/initial form values */
export const INITIAL_FORM_VALUES: CredentialFormValues = {
  name: '',
  credential_type: 'api_key',
  secret_data: '{}',
  expires_at: '',
};

/** Provider credential schema from client_metadata */
export interface CredentialSchema {
  properties: Record<string, CredentialSchemaField>;
  required?: string[];
  'x-ui-hints'?: {
    instructions?: string;
  };
}

export interface CredentialSchemaField {
  title?: string;
  description?: string;
  format?: string;
  examples?: string[];
  'x-ui-hints'?: {
    step?: number;
    step_title?: string;
    help_url?: string;
    help_link_text?: string;
    help_text?: string;
    generate_url_template?: string;
    generate_button_text?: string;
    depends_on?: string;
  };
}

/** Credential record returned from the API */
export interface Credential {
  id: string;
  name: string;
  credential_type: string;
  provider_id?: string;
  organization_id?: string;
  is_active: boolean;
  expires_at?: string | null;
  created_at?: string | null;
  updated_at?: string;
  has_client_credentials?: boolean;
  has_access_token?: boolean;
  is_token_type?: boolean;
}

/** Provider record (subset used in credentials page) */
export interface ProviderInfo {
  name: string;
  config?: {
    oauth_provider?: string;
  };
  client_metadata?: {
    credential_schema?: CredentialSchema;
  };
}

/** OAuth providers response shape */
export interface OAuthProviders {
  [key: string]: {
    available: boolean;
    scopes: string[];
    platform_configured?: boolean;
  };
}
