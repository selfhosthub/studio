// ui/app/workflows/[id]/edit/hooks/useWebhookConfig.ts

import { useState, useCallback } from 'react';
import { generateWorkflowWebhookToken, regenerateWorkflowWebhookToken, deleteWorkflowWebhookToken } from '@/shared/api';
import { buildWebhookUrl, buildCurlCommand, generateSecureToken } from '@/shared/lib/webhook-utils';
import { useToast } from '@/features/toast';
import { TIMEOUTS } from '@/shared/lib/constants';

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

  const webhookUrl = buildWebhookUrl(webhookToken);

  const initFromWorkflow = useCallback((workflowData: any) => {
    if (workflowData.webhook_method) {
      setWebhookMethod(workflowData.webhook_method as 'POST' | 'GET');
    }
    if (workflowData.webhook_auth_type) {
      setWebhookAuthType(workflowData.webhook_auth_type as 'none' | 'header' | 'jwt' | 'hmac');
    }
    if (workflowData.webhook_auth_header_value) {
      setWebhookAuthHeaderValue(workflowData.webhook_auth_header_value);
    }
    if (workflowData.webhook_jwt_secret) {
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
      const curlCommand = buildCurlCommand(webhookUrl, webhookMethod, webhookAuthType, webhookAuthHeaderValue, webhookJwtSecret);
      navigator.clipboard.writeText(curlCommand);
      setCopiedCurlCommand(true);
      setTimeout(() => setCopiedCurlCommand(false), TIMEOUTS.COPY_FEEDBACK);
    }
  }, [webhookUrl, webhookMethod, webhookAuthType, webhookAuthHeaderValue, webhookJwtSecret]);

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
