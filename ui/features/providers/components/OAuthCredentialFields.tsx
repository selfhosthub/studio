// ui/features/providers/components/OAuthCredentialFields.tsx

import React from 'react';

/** OAuth credential field values entered manually (non-schema providers). */
export interface OAuthFieldValues {
  access_token: string;
  refresh_token: string;
  client_id: string;
  client_secret: string;
}

export const EMPTY_OAUTH_FIELDS: OAuthFieldValues = {
  access_token: '',
  refresh_token: '',
  client_id: '',
  client_secret: '',
};

/** Build secret_data from OAuth fields, dropping empty optional keys. */
export function buildOAuthSecretData(f: OAuthFieldValues): Record<string, string> {
  const out: Record<string, string> = { access_token: f.access_token };
  if (f.refresh_token.trim()) out.refresh_token = f.refresh_token;
  if (f.client_id.trim()) out.client_id = f.client_id;
  if (f.client_secret.trim()) out.client_secret = f.client_secret;
  return out;
}

/** Populate OAuth fields from a revealed/stored secret_data record. */
export function oauthFieldsFromSecretData(data: Record<string, unknown>): OAuthFieldValues {
  return {
    access_token: String(data.access_token ?? ''),
    refresh_token: String(data.refresh_token ?? ''),
    client_id: String(data.client_id ?? ''),
    client_secret: String(data.client_secret ?? ''),
  };
}

interface OAuthCredentialFieldsProps {
  values: OAuthFieldValues;
  onChange: (values: OAuthFieldValues) => void;
  idPrefix?: string;
  isEdit?: boolean;
}

/** Multi-field OAuth credential inputs: access/refresh tokens + client id/secret. */
export function OAuthCredentialFields({
  values,
  onChange,
  idPrefix = '',
  isEdit = false,
}: OAuthCredentialFieldsProps) {
  const set =
    (key: keyof OAuthFieldValues) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      onChange({ ...values, [key]: e.target.value });

  return (
    <div className="space-y-3 mt-1">
      <div>
        <label htmlFor={`${idPrefix}oauth_access_token`} className="form-label text-xs">
          Access Token *
        </label>
        <input
          id={`${idPrefix}oauth_access_token`}
          type="text"
          required
          value={values.access_token}
          onChange={set('access_token')}
          className="form-input-mono"
          placeholder={isEdit ? 'Enter new access token...' : 'OAuth access token'}
          autoComplete="off"
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}oauth_refresh_token`} className="form-label text-xs">
          Refresh Token <span className="text-muted">(enables automatic re-authorization)</span>
        </label>
        <input
          id={`${idPrefix}oauth_refresh_token`}
          type="password"
          value={values.refresh_token}
          onChange={set('refresh_token')}
          className="form-input-mono"
          placeholder="OAuth refresh token"
          autoComplete="off"
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}oauth_client_id`} className="form-label text-xs">
          Client ID <span className="text-muted">(optional)</span>
        </label>
        <input
          id={`${idPrefix}oauth_client_id`}
          type="text"
          value={values.client_id}
          onChange={set('client_id')}
          className="form-input-mono"
          placeholder="OAuth client ID"
          autoComplete="off"
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}oauth_client_secret`} className="form-label text-xs">
          Client Secret <span className="text-muted">(optional)</span>
        </label>
        <input
          id={`${idPrefix}oauth_client_secret`}
          type="password"
          value={values.client_secret}
          onChange={set('client_secret')}
          className="form-input-mono"
          placeholder="OAuth client secret"
          autoComplete="off"
        />
      </div>
      <p className="form-helper">
        Stored as {'{'}&#34;access_token&#34;, &#34;refresh_token&#34;, &#34;client_id&#34;, &#34;client_secret&#34;{'}'}
      </p>
    </div>
  );
}
