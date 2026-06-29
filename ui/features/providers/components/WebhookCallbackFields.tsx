// ui/features/providers/components/WebhookCallbackFields.tsx

import { useState } from 'react';
import { TIMEOUTS } from '@/shared/lib/constants';
import { RefreshCw, Copy, Check, X } from 'lucide-react';
import { Modal } from '@/shared/ui';
import { getApiEndpoint } from '@/shared/lib/config';
import { generateSecureToken } from '@/shared/lib/webhook-utils';

interface WebhookCallbackFieldsProps {
  /** The callback API key value (held in schemaValues), generate-only. */
  callbackKey: string;
  setCallbackKey: (value: string) => void;
  /** The callback routing token; the URL is derived from it. Generate-only. */
  callbackToken: string | null;
  setCallbackToken: (value: string) => void;
}

type Pending = 'key' | 'url' | null;

/**
 * Webhook callback API key + callback URL, both generate-on-demand. Empty until
 * the user clicks Generate; regenerating an existing value confirms first (the
 * user must then update the provider with the new value). Either value can be
 * cleared, and the API key can be typed directly. Values persist only when the
 * credential is saved. The URL host is the public API base (getApiEndpoint),
 * correct behind a tunnel/proxy.
 */
export function WebhookCallbackFields({
  callbackKey,
  setCallbackKey,
  callbackToken,
  setCallbackToken,
}: WebhookCallbackFieldsProps) {
  const [copied, setCopied] = useState<Pending>(null);
  const [confirming, setConfirming] = useState<Pending>(null);

  const callbackUrl = callbackToken
    ? getApiEndpoint(`/webhooks/incoming/${callbackToken}`)
    : '';

  const doGenerateKey = () => setCallbackKey(generateSecureToken(32));
  const doGenerateUrl = () => setCallbackToken(generateSecureToken(32));

  const onGenerateKey = () => (callbackKey ? setConfirming('key') : doGenerateKey());
  const onGenerateUrl = () => (callbackToken ? setConfirming('url') : doGenerateUrl());

  const confirmRegenerate = () => {
    if (confirming === 'key') doGenerateKey();
    else if (confirming === 'url') doGenerateUrl();
    setConfirming(null);
  };

  const copy = async (which: 'key' | 'url', value: string) => {
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(which);
    setTimeout(() => setCopied(null), TIMEOUTS.COPY_FEEDBACK_SHORT);
  };

  return (
    <>
      <div>
        <label htmlFor="webhook_callback_url" className="form-label">
          Webhook Callback URL
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            id="webhook_callback_url"
            readOnly
            value={callbackUrl}
            placeholder="Not generated"
            className="form-input-mono flex-1 min-w-0"
          />
          <button
            type="button"
            onClick={onGenerateUrl}
            title="Generate new URL"
            aria-label="Generate new URL"
            className="px-3 py-2 bg-surface text-secondary rounded hover:opacity-80 transition-colors"
          >
            <RefreshCw size={16} />
          </button>
          <button
            type="button"
            onClick={() => setCallbackToken('')}
            disabled={!callbackToken}
            title="Clear callback URL"
            aria-label="Clear callback URL"
            className="px-3 py-2 bg-surface text-secondary rounded hover:opacity-80 transition-colors disabled:opacity-50"
          >
            <X size={16} />
          </button>
          <button
            type="button"
            onClick={() => copy('url', callbackUrl)}
            disabled={!callbackUrl}
            aria-label="Copy callback URL"
            className="px-3 py-2 bg-surface text-secondary rounded hover:opacity-80 transition-colors disabled:opacity-50"
          >
            {copied === 'url' ? <Check size={16} /> : <Copy size={16} />}
          </button>
        </div>
      </div>

      <div>
        <label htmlFor="webhook_callback_api_key" className="form-label">
          Webhook Callback API Key
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            id="webhook_callback_api_key"
            value={callbackKey}
            onChange={(e) => setCallbackKey(e.target.value)}
            placeholder="Not generated"
            className="form-input-mono flex-1 min-w-0"
          />
          <button
            type="button"
            onClick={onGenerateKey}
            title="Generate new API key"
            aria-label="Generate new API key"
            className="px-3 py-2 bg-surface text-secondary rounded hover:opacity-80 transition-colors"
          >
            <RefreshCw size={16} />
          </button>
          <button
            type="button"
            onClick={() => setCallbackKey('')}
            disabled={!callbackKey}
            title="Clear API key"
            aria-label="Clear API key"
            className="px-3 py-2 bg-surface text-secondary rounded hover:opacity-80 transition-colors disabled:opacity-50"
          >
            <X size={16} />
          </button>
          <button
            type="button"
            onClick={() => copy('key', callbackKey)}
            disabled={!callbackKey}
            aria-label="Copy callback API key"
            className="px-3 py-2 bg-surface text-secondary rounded hover:opacity-80 transition-colors disabled:opacity-50"
          >
            {copied === 'key' ? <Check size={16} /> : <Copy size={16} />}
          </button>
        </div>
      </div>

      {confirming && (
        <Modal isOpen onClose={() => setConfirming(null)} title="Regenerate?" size="sm">
          <div className="p-6 space-y-4">
            <p className="text-sm text-secondary">
              Regenerate? You&apos;ll need to update Leonardo with the new value.
            </p>
            <div className="flex justify-end gap-3">
              <button type="button" onClick={confirmRegenerate} className="btn-primary">
                Regenerate
              </button>
              <button type="button" onClick={() => setConfirming(null)} className="btn-secondary">
                Cancel
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
