// ui/features/providers/hooks/useCredentialForm.ts

import { useState, useCallback } from 'react';
import {
  createProviderCredential,
  updateProviderCredential,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import { getBrowserTimezone, utcIsoToZonedInput, zonedInputToUtcIso } from '@/shared/lib/schedule-utils';
import {
  buildOAuthSecretData,
  EMPTY_OAUTH_FIELDS,
  type OAuthFieldValues,
} from '../components/OAuthCredentialFields';
import type {
  CredentialFormValues,
  CredentialSchema,
  Credential,
} from '../credential-types';
import { INITIAL_FORM_VALUES, schemaCredentialType } from '../credential-types';

/** Converts a datetime-local value to a UTC ISO string, or null when blank. */
function expiresAtToUtc(local: string): string | null {
  return local ? zonedInputToUtcIso(local, getBrowserTimezone()) : null;
}

/** Keeps only the fields the user typed a value into. */
function typedOnly(values: Record<string, unknown>): Record<string, unknown> | undefined {
  const typed = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== '' && v != null));
  return Object.keys(typed).length ? typed : undefined;
}

interface UseCredentialFormOptions {
  providerId: string;
  credentialSchema: CredentialSchema | undefined;
  hasCredentialSchema: boolean;
  providerAuthType?: string;
  setCredentials: React.Dispatch<React.SetStateAction<Credential[]>>;
  onRevealedSecretInvalidate: (credentialId: string) => void;
}

export function useCredentialForm({
  providerId,
  credentialSchema,
  hasCredentialSchema,
  providerAuthType,
  setCredentials,
  onRevealedSecretInvalidate,
}: UseCredentialFormOptions) {
  const { toast } = useToast();

  // Modal visibility
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingCredential, setEditingCredential] = useState<Credential | null>(null);

  // Form fields
  const [credentialForm, setCredentialForm] = useState<CredentialFormValues>(INITIAL_FORM_VALUES);
  const [formError, setFormError] = useState<string | null>(null);
  const [useJsonMode, setUseJsonMode] = useState(false);
  const [simpleValue, setSimpleValue] = useState('');
  const [basicAuthUsername, setBasicAuthUsername] = useState('');
  const [basicAuthPassword, setBasicAuthPassword] = useState('');
  const [basicAuthPasswordConfirm, setBasicAuthPasswordConfirm] = useState('');
  const [oauthFields, setOauthFields] = useState<OAuthFieldValues>(EMPTY_OAUTH_FIELDS);
  const [schemaValues, setSchemaValues] = useState<Record<string, string>>({});
  // Callback URL routing token, held in form state and regeneratable client-side;
  // persists only when the user saves. Seeded from the credential on edit.
  const [webhookCallbackToken, setWebhookCallbackToken] = useState<string | null>(null);

  /** Reset all form fields to initial state */
  const resetForm = useCallback(() => {
    setCredentialForm(INITIAL_FORM_VALUES);
    setFormError(null);
    setUseJsonMode(false);
    setSimpleValue('');
    setBasicAuthUsername('');
    setBasicAuthPassword('');
    setBasicAuthPasswordConfirm('');
    setOauthFields(EMPTY_OAUTH_FIELDS);
    setSchemaValues({});
    setWebhookCallbackToken(null);
  }, []);

  /** Handle credential type change */
  const handleCredentialTypeChange = useCallback((newType: string) => {
    setCredentialForm(prev => ({ ...prev, credential_type: newType }));
    setUseJsonMode(newType === 'custom');
    setSimpleValue('');
    setBasicAuthUsername('');
    setBasicAuthPassword('');
    setBasicAuthPasswordConfirm('');
    setOauthFields(EMPTY_OAUTH_FIELDS);
  }, []);

  /** Open the add modal with reset state */
  const handleOpenAddModal = useCallback(() => {
    resetForm();
    setShowAddModal(true);
  }, [resetForm]);

  /** Close the add modal */
  const handleCloseAddModal = useCallback(() => {
    setShowAddModal(false);
    resetForm();
  }, [resetForm]);

  /** Close the edit modal */
  const handleCloseEditModal = useCallback(() => {
    setShowEditModal(false);
    setEditingCredential(null);
    resetForm();
  }, [resetForm]);

  /**
   * Build secret_data from form state, validating schema fields.
   * Returns null if validation fails (formError is set internally).
   */
  const buildSecretData = useCallback((): Record<string, unknown> | null => {
    if (hasCredentialSchema && credentialSchema) {
      const requiredFields = credentialSchema.required || [];
      for (const field of requiredFields) {
        if (!schemaValues[field]?.trim()) {
          const fieldTitle = credentialSchema.properties[field]?.title || field;
          setFormError(`${fieldTitle} is required`);
          return null;
        }
      }
      return { ...schemaValues };
    }

    if (useJsonMode) {
      try {
        return JSON.parse(credentialForm.secret_data);
      } catch {
        setFormError('Invalid JSON');
        return null;
      }
    }

    const type = credentialForm.credential_type;
    if (type === 'api_key') {
      return { api_key: simpleValue };
    }
    if (type === 'oauth') {
      if (!oauthFields.access_token.trim()) {
        setFormError('Access Token is required');
        return null;
      }
      return buildOAuthSecretData(oauthFields);
    }
    if (type === 'bearer') {
      return { access_token: simpleValue };
    }
    if (type === 'basic_auth') {
      if (basicAuthPassword !== basicAuthPasswordConfirm) {
        setFormError('Passwords do not match');
        return null;
      }
      return { username: basicAuthUsername, password: basicAuthPassword };
    }
    return { value: simpleValue };
  }, [
    hasCredentialSchema, credentialSchema, schemaValues,
    useJsonMode, credentialForm.secret_data, credentialForm.credential_type,
    simpleValue, basicAuthUsername, basicAuthPassword, basicAuthPasswordConfirm,
    oauthFields,
  ]);

  /**
   * Build secret_data for an update from the fields the user typed. Undefined keeps
   * the stored secret; null means validation failed (formError is set).
   */
  const buildSecretDataForUpdate = useCallback((): Record<string, unknown> | null | undefined => {
    if (hasCredentialSchema && credentialSchema) {
      return typedOnly(schemaValues);
    }

    if (useJsonMode) {
      const text = credentialForm.secret_data.trim();
      if (!text || text === '{}') return undefined;
      try {
        return JSON.parse(text);
      } catch {
        setFormError('Invalid JSON');
        return null;
      }
    }

    const type = credentialForm.credential_type;
    if (type === 'oauth') {
      return typedOnly(buildOAuthSecretData(oauthFields));
    }
    if (type === 'basic_auth') {
      if (basicAuthPassword && basicAuthPassword !== basicAuthPasswordConfirm) {
        setFormError('Passwords do not match');
        return null;
      }
      return typedOnly({ username: basicAuthUsername, password: basicAuthPassword });
    }
    if (!simpleValue) return undefined;
    if (type === 'api_key') return { api_key: simpleValue };
    if (type === 'bearer') return { access_token: simpleValue };
    return { value: simpleValue };
  }, [
    hasCredentialSchema, credentialSchema, schemaValues,
    useJsonMode, credentialForm.secret_data, credentialForm.credential_type,
    simpleValue, basicAuthUsername, basicAuthPassword, basicAuthPasswordConfirm,
    oauthFields,
  ]);

  /** Handle create credential form submission */
  const handleCreateCredential = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!credentialForm.name.trim()) {
      setFormError('Credential name is required');
      return;
    }

    const secretData = buildSecretData();
    if (secretData === null) return;

    try {
      const credType = hasCredentialSchema ? schemaCredentialType(providerAuthType) : credentialForm.credential_type;
      const newCred = await createProviderCredential(providerId, {
        name: credentialForm.name,
        credential_type: credType,
        secret_data: secretData,
        expires_at: expiresAtToUtc(credentialForm.expires_at),
        webhook_callback_token: webhookCallbackToken,
      });
      setCredentials(prev => [...prev, newCred]);
      setShowAddModal(false);
      resetForm();
      toast({ title: 'Credential added', description: 'The credential was created successfully.', variant: 'success' });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create credential';
      setFormError(message);
    }
  }, [credentialForm, buildSecretData, hasCredentialSchema, providerAuthType, providerId, webhookCallbackToken, setCredentials, resetForm, toast]);

  /** Open the edit modal with the credential's settings; secret fields start empty */
  const handleEditClick = useCallback((credential: Credential) => {
    setEditingCredential(credential);
    const credType = credential.credential_type;

    setCredentialForm({
      name: credential.name,
      credential_type: credType,
      secret_data: '{}',
      expires_at: utcIsoToZonedInput(credential.expires_at ?? null, getBrowserTimezone()),
    });
    setFormError(null);
    setSimpleValue('');
    setBasicAuthUsername('');
    setBasicAuthPassword('');
    setBasicAuthPasswordConfirm('');
    setOauthFields(EMPTY_OAUTH_FIELDS);
    setSchemaValues({});
    setWebhookCallbackToken(credential.webhook_callback_token ?? null);
    setUseJsonMode(credType === 'custom' && !hasCredentialSchema);
    setShowEditModal(true);
  }, [hasCredentialSchema]);

  /** Handle update credential form submission */
  const handleUpdateCredential = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!credentialForm.name.trim()) {
      setFormError('Credential name is required');
      return;
    }

    const secretData = buildSecretDataForUpdate();
    if (secretData === null) return;

    try {
      const updatedCred = await updateProviderCredential(editingCredential!.id, {
        name: credentialForm.name,
        ...(secretData !== undefined && { secret_data: secretData }),
        expires_at: expiresAtToUtc(credentialForm.expires_at),
        webhook_callback_token: webhookCallbackToken,
      });
      setCredentials(prev => prev.map(c => c.id === editingCredential!.id ? updatedCred : c));
      onRevealedSecretInvalidate(editingCredential!.id);
      setShowEditModal(false);
      setEditingCredential(null);
      resetForm();
      toast({ title: 'Credential updated', description: 'The credential was updated successfully.', variant: 'success' });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to update credential';
      setFormError(message);
    }
  }, [credentialForm, buildSecretDataForUpdate, editingCredential, webhookCallbackToken, setCredentials, onRevealedSecretInvalidate, resetForm, toast]);

  return {
    // Modal state
    showAddModal,
    showEditModal,
    editingCredential,
    handleOpenAddModal,
    handleCloseAddModal,
    handleCloseEditModal,
    handleEditClick,

    // Form state
    credentialForm,
    setCredentialForm,
    formError,
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
    oauthFields,
    setOauthFields,
    schemaValues,
    setSchemaValues,
    webhookCallbackToken,
    setWebhookCallbackToken,
    handleCredentialTypeChange,

    // Actions
    handleCreateCredential,
    handleUpdateCredential,
  };
}
