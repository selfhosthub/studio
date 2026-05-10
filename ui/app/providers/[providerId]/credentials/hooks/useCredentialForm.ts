// ui/app/providers/[providerId]/credentials/hooks/useCredentialForm.ts

import { useState, useCallback } from 'react';
import {
  createProviderCredential,
  updateProviderCredential,
  revealProviderCredential,
  isCredentialTypeRevealable,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import type {
  CredentialFormValues,
  CredentialSchema,
  Credential,
} from '../types';
import { INITIAL_FORM_VALUES } from '../types';

interface UseCredentialFormOptions {
  providerId: string;
  credentialSchema: CredentialSchema | undefined;
  hasCredentialSchema: boolean;
  setCredentials: React.Dispatch<React.SetStateAction<Credential[]>>;
  onRevealedSecretInvalidate: (credentialId: string) => void;
}

export function useCredentialForm({
  providerId,
  credentialSchema,
  hasCredentialSchema,
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
  const [schemaValues, setSchemaValues] = useState<Record<string, string>>({});

  /** Reset all form fields to initial state */
  const resetForm = useCallback(() => {
    setCredentialForm(INITIAL_FORM_VALUES);
    setFormError(null);
    setUseJsonMode(false);
    setSimpleValue('');
    setBasicAuthUsername('');
    setBasicAuthPassword('');
    setBasicAuthPasswordConfirm('');
    setSchemaValues({});
  }, []);

  /** Handle credential type change */
  const handleCredentialTypeChange = useCallback((newType: string) => {
    setCredentialForm(prev => ({ ...prev, credential_type: newType }));
    setUseJsonMode(newType === 'custom');
    setSimpleValue('');
    setBasicAuthUsername('');
    setBasicAuthPassword('');
    setBasicAuthPasswordConfirm('');
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
    if (type === 'bearer' || type === 'oauth') {
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
  ]);

  /**
   * Build secret_data for an update (edit). Handles the basic_auth password
   * preservation logic when password is left blank.
   */
  const buildSecretDataForUpdate = useCallback(async (): Promise<Record<string, unknown> | null> => {
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
    if (type === 'bearer' || type === 'oauth') {
      return { access_token: simpleValue };
    }
    if (type === 'basic_auth') {
      if (basicAuthPassword && basicAuthPassword !== basicAuthPasswordConfirm) {
        setFormError('Passwords do not match');
        return null;
      }
      let passwordToUse = basicAuthPassword;
      if (!passwordToUse && editingCredential) {
        try {
          const existing = await revealProviderCredential(editingCredential.id);
          passwordToUse = (existing.secret_data as Record<string, string>)?.password || '';
        } catch {
          setFormError('Failed to retrieve existing password. Please enter a new password.');
          return null;
        }
      }
      return { username: basicAuthUsername, password: passwordToUse };
    }
    return { value: simpleValue };
  }, [
    hasCredentialSchema, credentialSchema, schemaValues,
    useJsonMode, credentialForm.secret_data, credentialForm.credential_type,
    simpleValue, basicAuthUsername, basicAuthPassword, basicAuthPasswordConfirm,
    editingCredential,
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
      const credType = hasCredentialSchema ? 'custom' : credentialForm.credential_type;
      const newCred = await createProviderCredential(providerId, {
        name: credentialForm.name,
        credential_type: credType,
        secret_data: secretData,
        expires_at: credentialForm.expires_at || null,
      });
      setCredentials(prev => [...prev, newCred]);
      setShowAddModal(false);
      resetForm();
      toast({ title: 'Credential added', description: 'The credential was created successfully.', variant: 'success' });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create credential';
      setFormError(message);
    }
  }, [credentialForm, buildSecretData, hasCredentialSchema, providerId, setCredentials, resetForm, toast]);

  /** Open the edit modal and populate form with existing values */
  const handleEditClick = useCallback(async (credential: Credential) => {
    setEditingCredential(credential);
    const credType = credential.credential_type;

    setCredentialForm({
      name: credential.name,
      credential_type: credType,
      secret_data: '{}',
      expires_at: credential.expires_at
        ? new Date(credential.expires_at).toISOString().slice(0, 16)
        : '',
    });
    setSimpleValue('');
    setBasicAuthUsername('');
    setBasicAuthPassword('');
    setBasicAuthPasswordConfirm('');
    setSchemaValues({});
    setUseJsonMode(credType === 'custom' && !hasCredentialSchema);

    if (isCredentialTypeRevealable(credType, credential.is_token_type)) {
      try {
        const result = await revealProviderCredential(credential.id);
        const secretData = result.secret_data || {};

        if (hasCredentialSchema) {
          setSchemaValues(secretData as Record<string, string>);
        } else {
          const keys = Object.keys(secretData);
          if (credType === 'basic_auth') {
            setBasicAuthUsername((secretData as Record<string, string>).username || '');
          } else if (keys.length > 1 || credType === 'custom') {
            setUseJsonMode(true);
            setCredentialForm(prev => ({
              ...prev,
              secret_data: JSON.stringify(secretData, null, 2),
            }));
          } else if (keys.length === 1) {
            setSimpleValue((secretData as Record<string, string>)[keys[0]] || '');
          }
        }
      } catch {
        // Fallback - user must re-enter values
      }
    }

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

    const secretData = await buildSecretDataForUpdate();
    if (secretData === null) return;

    try {
      const updatedCred = await updateProviderCredential(editingCredential!.id, {
        name: credentialForm.name,
        secret_data: secretData,
        expires_at: credentialForm.expires_at || null,
      } as Parameters<typeof updateProviderCredential>[1]);
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
  }, [credentialForm, buildSecretDataForUpdate, editingCredential, setCredentials, onRevealedSecretInvalidate, resetForm, toast]);

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
    schemaValues,
    setSchemaValues,
    handleCredentialTypeChange,

    // Actions
    handleCreateCredential,
    handleUpdateCredential,
  };
}
