// ui/app/providers/[providerId]/credentials/components/LegacyCredentialFields.tsx

import type { CredentialFormValues } from '../types';

interface LegacyCredentialFieldsProps {
  credentialForm: CredentialFormValues;
  setCredentialForm: React.Dispatch<React.SetStateAction<CredentialFormValues>>;
  useJsonMode: boolean;
  setUseJsonMode: React.Dispatch<React.SetStateAction<boolean>>;
  simpleValue: string;
  setSimpleValue: React.Dispatch<React.SetStateAction<string>>;
  basicAuthUsername: string;
  setBasicAuthUsername: React.Dispatch<React.SetStateAction<string>>;
  basicAuthPassword: string;
  setBasicAuthPassword: React.Dispatch<React.SetStateAction<string>>;
  basicAuthPasswordConfirm: string;
  setBasicAuthPasswordConfirm: React.Dispatch<React.SetStateAction<string>>;
  handleCredentialTypeChange: (newType: string) => void;
  /** Whether this is the edit modal (affects labels and placeholders) */
  isEdit?: boolean;
  idPrefix?: string;
}

/**
 * Legacy credential type dropdown + secret value input fields.
 * Used for providers that don't have a credential_schema.
 */
export function LegacyCredentialFields({
  credentialForm,
  setCredentialForm,
  useJsonMode,
  setUseJsonMode,
  simpleValue,
  setSimpleValue,
  basicAuthUsername,
  setBasicAuthUsername,
  basicAuthPassword,
  setBasicAuthPassword,
  basicAuthPasswordConfirm,
  setBasicAuthPasswordConfirm,
  handleCredentialTypeChange,
  isEdit = false,
  idPrefix = '',
}: LegacyCredentialFieldsProps) {
  const prefix = idPrefix || (isEdit ? 'edit-' : '');

  return (
    <>
      {/* Credential type dropdown */}
      <div>
        <label htmlFor={`${prefix}credential_type`} className="form-label">
          Credential Type *
        </label>
        <select
          id={`${prefix}credential_type`}
          value={credentialForm.credential_type}
          onChange={(e) => handleCredentialTypeChange(e.target.value)}
          className="form-select w-full"
        >
          <option value="api_key">API Key</option>
          <option value="oauth">OAuth Token</option>
          <option value="bearer">Bearer Token</option>
          <option value="basic_auth">Basic Auth</option>
          <option value="custom">Custom</option>
        </select>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label htmlFor={`${prefix}secret_data`} className="form-label">
            Secret Value *
          </label>
          <button
            type="button"
            onClick={() => setUseJsonMode(!useJsonMode)}
            className="text-xs text-info hover:text-info"
          >
            {useJsonMode ? '\u2190 Simple Mode' : 'JSON Mode \u2192'}
          </button>
        </div>

        {/* Security notice (edit only) */}
        {isEdit && (
          <div className="mb-2 alert alert-warning text-xs">
            {credentialForm.credential_type === 'basic_auth'
              ? 'Username is pre-filled. Leave password blank to keep existing password.'
              : 'For security, existing secret values are not displayed. Enter the new value to update.'}
          </div>
        )}

        {!useJsonMode ? (
          credentialForm.credential_type === 'basic_auth' ? (
            <BasicAuthFields
              basicAuthUsername={basicAuthUsername}
              setBasicAuthUsername={setBasicAuthUsername}
              basicAuthPassword={basicAuthPassword}
              setBasicAuthPassword={setBasicAuthPassword}
              basicAuthPasswordConfirm={basicAuthPasswordConfirm}
              setBasicAuthPasswordConfirm={setBasicAuthPasswordConfirm}
              isEdit={isEdit}
            />
          ) : (
            <SimpleValueField
              credentialType={credentialForm.credential_type}
              simpleValue={simpleValue}
              setSimpleValue={setSimpleValue}
              fieldId={`${prefix}secret_data`}
              isEdit={isEdit}
            />
          )
        ) : (
          <JsonModeField
            credentialForm={credentialForm}
            setCredentialForm={setCredentialForm}
            fieldId={`${prefix}secret_data`}
          />
        )}
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/*  Internal sub-components                                                    */
/* -------------------------------------------------------------------------- */

function BasicAuthFields({
  basicAuthUsername,
  setBasicAuthUsername,
  basicAuthPassword,
  setBasicAuthPassword,
  basicAuthPasswordConfirm,
  setBasicAuthPasswordConfirm,
  isEdit,
}: {
  basicAuthUsername: string;
  setBasicAuthUsername: React.Dispatch<React.SetStateAction<string>>;
  basicAuthPassword: string;
  setBasicAuthPassword: React.Dispatch<React.SetStateAction<string>>;
  basicAuthPasswordConfirm: string;
  setBasicAuthPasswordConfirm: React.Dispatch<React.SetStateAction<string>>;
  isEdit: boolean;
}) {
  return (
    <div className="space-y-3 mt-1">
      <div>
        <label className="form-label text-xs">
          {isEdit ? 'Username *' : 'Username'}
        </label>
        <input
          type="text"
          required
          value={basicAuthUsername}
          onChange={(e) => setBasicAuthUsername(e.target.value)}
          className="form-input"
          placeholder="Username"
          autoComplete="off"
        />
      </div>
      <div>
        <label className="form-label text-xs">
          {isEdit ? (
            <>New Password <span className="text-muted">(leave blank to keep existing)</span></>
          ) : (
            'Password'
          )}
        </label>
        <input
          type="password"
          required={!isEdit}
          value={basicAuthPassword}
          onChange={(e) => setBasicAuthPassword(e.target.value)}
          className="form-input"
          placeholder={isEdit ? 'Enter new password or leave blank' : 'Password'}
          autoComplete="off"
        />
      </div>
      {/* Show confirm only when adding or when a new password is entered during edit */}
      {(!isEdit || basicAuthPassword) && (
        <div>
          <label className="form-label text-xs">
            {isEdit ? 'Confirm New Password' : 'Confirm Password'}
          </label>
          <input
            type="password"
            required={!isEdit}
            value={basicAuthPasswordConfirm}
            onChange={(e) => setBasicAuthPasswordConfirm(e.target.value)}
            className={`form-input ${
              basicAuthPasswordConfirm && basicAuthPassword !== basicAuthPasswordConfirm
                ? 'border-danger'
                : ''
            }`}
            placeholder={isEdit ? 'Confirm new password...' : 'Confirm password'}
            autoComplete="off"
          />
          {basicAuthPasswordConfirm && basicAuthPassword !== basicAuthPasswordConfirm && (
            <p className="mt-1 text-xs text-danger">Passwords do not match</p>
          )}
        </div>
      )}
      <p className="form-helper">
        Stored as {"{"}&#34;username&#34;: &#34;...&#34;, &#34;password&#34;: &#34;...&#34;{"}"}
      </p>
    </div>
  );
}

function SimpleValueField({
  credentialType,
  simpleValue,
  setSimpleValue,
  fieldId,
  isEdit,
}: {
  credentialType: string;
  simpleValue: string;
  setSimpleValue: React.Dispatch<React.SetStateAction<string>>;
  fieldId: string;
  isEdit: boolean;
}) {
  const placeholders: Record<string, string> = isEdit
    ? {
        api_key: 'Enter new API key...',
        bearer: 'Enter new bearer token...',
        oauth: 'Enter new access token...',
      }
    : {
        api_key: 'sk-...',
        bearer: 'Bearer token',
        oauth: 'OAuth access token',
      };

  const storageHints: Record<string, string> = {
    api_key: 'Stored as {"api_key": "..."}',
    bearer: 'Stored as {"access_token": "..."}',
    oauth: 'Stored as {"access_token": "..."}',
    custom: 'Use JSON mode for custom structure',
  };

  return (
    <>
      <input
        type="text"
        id={fieldId}
        required
        value={simpleValue}
        onChange={(e) => setSimpleValue(e.target.value)}
        className="form-input-mono"
        placeholder={placeholders[credentialType] || (isEdit ? 'Enter new secret value...' : 'Your secret value')}
        autoComplete="off"
      />
      <p className="form-helper">
        {storageHints[credentialType] || ''}
      </p>
    </>
  );
}

function JsonModeField({
  credentialForm,
  setCredentialForm,
  fieldId,
}: {
  credentialForm: CredentialFormValues;
  setCredentialForm: React.Dispatch<React.SetStateAction<CredentialFormValues>>;
  fieldId: string;
}) {
  const placeholders: Record<string, string> = {
    api_key: '{"api_key": "sk-...", "api_secret": "..."}',
    oauth: '{"access_token": "...", "refresh_token": "..."}',
    basic_auth: '{"username": "...", "password": "..."}',
  };

  return (
    <>
      <textarea
        id={fieldId}
        required
        rows={6}
        value={credentialForm.secret_data}
        onChange={(e) => setCredentialForm({ ...credentialForm, secret_data: e.target.value })}
        className="form-textarea font-mono text-xs"
        placeholder={placeholders[credentialForm.credential_type] || '{"key": "value"}'}
      />
      <p className="form-helper">
        Advanced: Enter credential data as JSON
      </p>
    </>
  );
}
