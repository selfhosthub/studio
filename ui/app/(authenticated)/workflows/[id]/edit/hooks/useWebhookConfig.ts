// ui/app/(authenticated)/workflows/[id]/edit/hooks/useWebhookConfig.ts

import { useState, useCallback, useEffect } from 'react';
import { generateWorkflowWebhookToken, regenerateWorkflowWebhookToken, deleteWorkflowWebhookToken, getWorkflowFormSchema } from '@/shared/api';
import { buildWebhookUrl, buildCurlCommand, buildTriggerSampleBody, generateSecureToken } from '@/shared/lib/webhook-utils';
import { useToast } from '@/features/toast';
import { TIMEOUTS, CONFIGURED_SENTINEL } from '@/shared/lib/constants';

export function useWebhookConfig(workflowId: string, webhookToken: string | null) {
  const { toast } = useToast();

  const [webhookTokenLoading, setWebhookTokenLoading] = useState(false);
  const [copiedWebhookUrl, setCopiedWebhookUrl] = useState(false);
  const [copiedCurlCommand, setCopiedCurlCommand] = useState(false);
  const [copiedSigningSecret, setCopiedSigningSecret] = useState(false);
  const [webhookMethod, setWebhookMethod] = useState<'POST' | 'GET'>('POST');
  const [webhookAuthType, setWebhookAuthType] = useState<'none' | 'header' | 'jwt' | 'hmac'>('none');
  const [webhookAuthHeaderValue, setWebhookAuthHeaderValue] = useState('');
  const [webhookJwtSecret, setWebhookJwtSecret] = useState('');
  const [showWebhookAuthValue, setShowWebhookAuthValue] = useState(false);
  const [generatingAuth, setGeneratingAuth] = useState(false);
  const [showHmacHelpModal, setShowHmacHelpModal] = useState(false);
  // Pre-populate the curl body with field_id-keyed defaults from the form schema.
  const [sampleBody, setSampleBody] = useState('{"key": "value"}');

  const webhookUrl = buildWebhookUrl(webhookToken);

  useEffect(() => {
    let cancelled = false;
    getWorkflowFormSchema(workflowId)
      .then((schema) => {
        if (!cancelled && schema.fields.length > 0) {
          setSampleBody(buildTriggerSampleBody(schema.fields));
        }
      })
      .catch(() => {
        // Fall back to the generic placeholder body; the snippet still works.
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  const initFromWorkflow = useCallback((workflowData: any) => {
    if (workflowData.webhook_method) {
      setWebhookMethod(workflowData.webhook_method as 'POST' | 'GET');
    }
    if (workflowData.webhook_auth_type) {
      setWebhookAuthType(workflowData.webhook_auth_type as 'none' | 'header' | 'jwt' | 'hmac');
    }
    // Secret-class values come back masked as the CONFIGURED sentinel, never
    // plaintext. Don't pre-fill the sentinel into the editable field; leaving it
    // blank means "keep existing" (the API ignores the sentinel on save).
    if (
      workflowData.webhook_auth_header_value &&
      workflowData.webhook_auth_header_value !== CONFIGURED_SENTINEL
    ) {
      setWebhookAuthHeaderValue(workflowData.webhook_auth_header_value);
    }
    if (
      workflowData.webhook_jwt_secret &&
      workflowData.webhook_jwt_secret !== CONFIGURED_SENTINEL
    ) {
      setWebhookJwtSecret(workflowData.webhook_jwt_secret);
    }
  }, []);

  const handleGenerateToken = useCallback(async (): Promise<{ webhook_token: string; webhook_secret: string } | null> => {
    try {
      setWebhookTokenLoading(true);
      const response = await generateWorkflowWebhookToken(workflowId);
      return response;
    } catch (err: unknown) {
      toast({ title: 'Failed to generate webhook URL', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
      return null;
    } finally {
      setWebhookTokenLoading(false);
    }
  }, [workflowId, toast]);

  const handleRegenerateToken = useCallback(async (): Promise<{ webhook_token: string; webhook_secret: string } | null> => {
    if (!webhookToken) return null;

    if (!confirm('Are you sure you want to regenerate the webhook URL? The old URL will stop working immediately and any integrations using it will break.')) {
      return null;
    }

    try {
      setWebhookTokenLoading(true);
      const response = await regenerateWorkflowWebhookToken(workflowId);
      toast({ title: 'Webhook URL regenerated', description: 'Make sure to update any integrations with the new URL.', variant: 'success' });
      return response;
    } catch (err: unknown) {
      toast({ title: 'Failed to regenerate webhook URL', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
      return null;
    } finally {
      setWebhookTokenLoading(false);
    }
  }, [workflowId, webhookToken, toast]);

  const handleDeleteToken = useCallback(async (): Promise<boolean> => {
    if (!webhookToken) return false;

    try {
      setWebhookTokenLoading(true);
      await deleteWorkflowWebhookToken(workflowId);
      return true;
    } catch (err: unknown) {
      toast({ title: 'Failed to delete webhook URL', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
      return false;
    } finally {
      setWebhookTokenLoading(false);
    }
  }, [workflowId, webhookToken, toast]);

  const handleCopyWebhookUrl = useCallback(() => {
    if (webhookUrl) {
      navigator.clipboard.writeText(webhookUrl);
      setCopiedWebhookUrl(true);
      setTimeout(() => setCopiedWebhookUrl(false), TIMEOUTS.COPY_FEEDBACK);
    }
  }, [webhookUrl]);

  const handleCopyCurlCommand = useCallback(() => {
    if (webhookUrl) {
      const curlCommand = buildCurlCommand(webhookUrl, webhookMethod, webhookAuthType, webhookAuthHeaderValue, webhookJwtSecret, sampleBody);
      navigator.clipboard.writeText(curlCommand);
      setCopiedCurlCommand(true);
      setTimeout(() => setCopiedCurlCommand(false), TIMEOUTS.COPY_FEEDBACK);
    }
  }, [webhookUrl, webhookMethod, webhookAuthType, webhookAuthHeaderValue, webhookJwtSecret, sampleBody]);

  const handleGenerateAuthToken = useCallback(() => {
    setGeneratingAuth(true);
    const token = generateSecureToken(32);
    if (webhookAuthType === 'header') {
      setWebhookAuthHeaderValue(token);
    } else if (webhookAuthType === 'jwt') {
      setWebhookJwtSecret(token);
    }
    setGeneratingAuth(false);
  }, [webhookAuthType]);

  return {
    webhookAuthType,
    setWebhookAuthType,
    webhookAuthHeaderValue,
    setWebhookAuthHeaderValue,
    webhookJwtSecret,
    setWebhookJwtSecret,
    webhookMethod,
    setWebhookMethod,
    webhookUrl,
    handleGenerateToken,
    handleRegenerateToken,
    handleDeleteToken,
    webhookTokenLoading,
    handleCopyWebhookUrl,
    copiedWebhookUrl,
    handleCopyCurlCommand,
    copiedCurlCommand,
    copiedSigningSecret,
    setCopiedSigningSecret,
    showWebhookAuthValue,
    setShowWebhookAuthValue,
    generatingAuth,
    handleGenerateAuthToken,
    showHmacHelpModal,
    setShowHmacHelpModal,
    initFromWorkflow,
  };
}
