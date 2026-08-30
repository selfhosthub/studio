// ui/features/providers/credential-types.ts

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
  /** Provider-JSON UI hints (the `ui` object on credential_schema fields). */
  ui?: {
    order?: number;
    placeholder?: string;
    help_url?: string;
    readonly?: boolean;
    hidden?: boolean;
  };
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
  has_refresh_token?: boolean;
  /** True when the credential holds a webhook_callback_api_key (webhook-capable). */
  has_webhook_callback_key?: boolean;
  /** Stable routing key for this credential's inbound callback URL; null until first webhook save. */
  webhook_callback_token?: string | null;
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
