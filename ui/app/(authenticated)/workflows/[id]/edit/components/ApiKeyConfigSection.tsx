// ui/app/(authenticated)/workflows/[id]/edit/components/ApiKeyConfigSection.tsx

'use client';

import React, { useEffect, useState } from 'react';
import { Copy, Check, RefreshCw } from 'lucide-react';
import { AlertTriangle } from 'lucide-react';
import { generateWorkflowApiKey, regenerateWorkflowApiKey, clearWorkflowApiKey, recallWorkflowApiKey, setWorkflowTriggerSecret, getWorkflowFormSchema } from '@/shared/api';
import { buildTriggerSampleBody } from '@/shared/lib/webhook-utils';
import { useToast } from '@/features/toast';
import { TIMEOUTS } from '@/shared/lib/constants';
import { TriggerSecretPicker } from './TriggerSecretPicker';

interface ApiKeyConfigSectionProps {
  workflowId: string;
  /** True when an API key already exists for this workflow. The value is now
   *  recoverable: admins recall it via GET; non-admins get 403 and never see it. */
  hasApiKey: boolean;
  onChanged: (hasApiKey: boolean) => void;
}

function buildApiKeyCurl(triggerUrl: string, apiKey: string, body: string): string {
  return `curl -X POST ${triggerUrl} -H "Authorization: Bearer ${apiKey}" -H "Content-Type: application/json" -d '${body}'`;
}

export function ApiKeyConfigSection({ workflowId, hasApiKey, onChanged }: ApiKeyConfigSectionProps) {
  const { toast } = useToast();

  const [apiKey, setApiKey] = useState<string | null>(null);
  const [triggerUrl, setTriggerUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedCurl, setCopiedCurl] = useState(false);
  // Pre-populate the curl body with field_id-keyed defaults from the form schema.
  const [sampleBody, setSampleBody] = useState('{}');
  // Workflows sharing this key's trigger secret (incl. this one). >1 → regeneration
  // is deferred to the Secrets page so it's deliberate across every sharer.
  const [sharedByCount, setSharedByCount] = useState(1);

  useEffect(() => {
    let cancelled = false;
    getWorkflowFormSchema(workflowId)
      .then((schema) => {
        if (!cancelled) setSampleBody(buildTriggerSampleBody(schema.fields));
      })
      .catch(() => {
        // Fall back to an empty body; the snippet still works.
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  // Recall the existing key for admins (it's recoverable now). A non-admin gets
  // 403 and the key stays hidden; the "configured" fallback message shows.
  useEffect(() => {
    if (!hasApiKey) return;
    let cancelled = false;
    recallWorkflowApiKey(workflowId)
      .then((result) => {
        if (!cancelled) {
          setApiKey(result.api_key);
          setTriggerUrl(result.trigger_url);
          setSharedByCount(result.shared_by_count ?? 1);
        }
      })
      .catch(() => {
        // No key / not permitted - leave hidden.
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId, hasApiKey]);

  const handleUseExisting = async (secretId: string) => {
    if (!secretId) return;
    setLoading(true);
    try {
      await setWorkflowTriggerSecret(workflowId, secretId);
      onChanged(true);
      const result = await recallWorkflowApiKey(workflowId);
      setApiKey(result.api_key);
      setTriggerUrl(result.trigger_url);
      setSharedByCount(result.shared_by_count ?? 1);
      toast({ title: 'Trigger secret linked', variant: 'success' });
    } catch (err: unknown) {
      toast({ title: 'Failed to link secret', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async (regenerate: boolean) => {
    if (regenerate && !confirm('Regenerate the API key? The old key will stop working immediately and any integrations using it will break.')) {
      return;
    }
    setLoading(true);
    try {
      const result = regenerate
        ? await regenerateWorkflowApiKey(workflowId)
        : await generateWorkflowApiKey(workflowId);
      setApiKey(result.api_key);
      setTriggerUrl(result.trigger_url);
      setSharedByCount(result.shared_by_count ?? 1);
      onChanged(true);
      toast({
        title: regenerate ? 'API key regenerated' : 'API key generated',
        description: 'Copy it to configure your integration.',
        variant: 'success',
      });
    } catch (err: unknown) {
      toast({ title: 'Failed to generate API key', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const shared = sharedByCount > 1;

  const handleRemove = async () => {
    const message = shared
      ? `Unlink this workflow from the shared trigger secret? The other ${sharedByCount - 1} workflow(s) using it keep working; only this workflow stops.`
      : 'Remove the API key for this workflow? Integrations using it will stop working.';
    if (!confirm(message)) {
      return;
    }
    setLoading(true);
    try {
      await clearWorkflowApiKey(workflowId);
      setApiKey(null);
      setTriggerUrl(null);
      setSharedByCount(1);
      onChanged(false);
      toast({ title: shared ? 'Workflow unlinked from secret' : 'API key removed', variant: 'success' });
    } catch (err: unknown) {
      toast({ title: 'Failed to remove API key', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleCopyKey = () => {
    if (apiKey) {
      navigator.clipboard.writeText(apiKey);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), TIMEOUTS.COPY_FEEDBACK);
    }
  };

  const handleCopyCurl = () => {
    if (apiKey && triggerUrl) {
      navigator.clipboard.writeText(buildApiKeyCurl(triggerUrl, apiKey, sampleBody));
      setCopiedCurl(true);
      setTimeout(() => setCopiedCurl(false), TIMEOUTS.COPY_FEEDBACK);
    }
  };

  return (
    <div className="md:col-span-2 p-3 bg-surface rounded-md border border-primary">
      <div className="space-y-3">
        {apiKey ? (
          <>
            {/* Admin-only, recoverable secret */}
            <div className="flex items-start gap-2 text-xs text-secondary">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>Visible to organization admins only. Copy it to configure your integration.</span>
            </div>

            {/* Key + copy */}
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs text-secondary flex-shrink-0">Key:</span>
              <input
                type="text"
                readOnly
                value={apiKey}
                className="form-input-mono form-input-readonly flex-1 min-w-0 text-xs py-1.5"
              />
              <button
                type="button"
                onClick={handleCopyKey}
                className="btn-secondary btn-with-icon p-1.5 flex-shrink-0"
                title="Copy API key"
              >
                {copiedKey ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>

            {/* cURL example */}
            {triggerUrl && (
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs text-secondary flex-shrink-0">cURL:</span>
                <input
                  type="text"
                  readOnly
                  value={buildApiKeyCurl(triggerUrl, apiKey, sampleBody)}
                  className="form-input-mono form-input-readonly flex-1 min-w-0 text-xs py-1.5"
                />
                <button
                  type="button"
                  onClick={handleCopyCurl}
                  className="btn-secondary text-xs px-2 py-1.5 flex-shrink-0"
                  title="Copy cURL command"
                >
                  {copiedCurl ? <Check className="h-4 w-4 text-success" /> : 'cURL'}
                </button>
              </div>
            )}
          </>
        ) : hasApiKey ? (
          <p className="text-muted text-xs">
            An API key is configured. Only organization admins can view it.
          </p>
        ) : (
          <p className="text-muted text-xs">
            Generate an API key to trigger this workflow over HTTP with a bearer token.
          </p>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-3">
          {!hasApiKey && !apiKey ? (
            <TriggerSecretPicker
              workflowId={workflowId}
              secretType="api_key"
              generateLabel={loading ? 'Generating...' : 'Generate API key'}
              onGenerate={() => handleGenerate(false)}
              onLinked={handleUseExisting}
              disabled={loading}
            />
          ) : (
            <>
              {shared ? (
                <span className="text-xs text-secondary">
                  Shared by {sharedByCount} workflows.{' '}
                  <a href="/secrets?tab=organization" className="text-info hover:underline">
                    Regenerate from the Secrets page
                  </a>{' '}
                  so the rotation is deliberate across all of them.
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => handleGenerate(true)}
                  disabled={loading}
                  className="text-xs text-secondary hover:text-primary inline-flex items-center"
                >
                  <RefreshCw className="h-3 w-3 mr-1" />
                  Regenerate
                </button>
              )}
              <button
                type="button"
                onClick={handleRemove}
                disabled={loading}
                className="text-xs text-secondary hover:text-danger inline-flex items-center"
              >
                {shared ? 'Unlink' : 'Remove'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
