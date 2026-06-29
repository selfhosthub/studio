// ui/features/providers/components/OAuthRedirectUri.tsx

'use client';

import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { TIMEOUTS } from '@/shared/lib/constants';

interface OAuthRedirectUriProps {
  redirectUri: string;
}

/** Copyable OAuth callback URL to register in the provider's OAuth app. */
export function OAuthRedirectUri({ redirectUri }: OAuthRedirectUriProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(redirectUri);
    setCopied(true);
    setTimeout(() => setCopied(false), TIMEOUTS.COPY_FEEDBACK_SHORT);
  };

  return (
    <div className="alert alert-info">
      <p className="text-sm font-medium text-info">OAuth redirect URI</p>
      <p className="mt-1 text-xs text-info">
        Register this exact URL as an authorized redirect URI in your provider&apos;s OAuth app.
      </p>
      <div className="mt-2 flex items-center gap-2">
        <code className="flex-1 break-all rounded bg-info-subtle px-2 py-1 text-xs">
          {redirectUri}
        </code>
        <button
          type="button"
          onClick={handleCopy}
          className="btn-secondary btn-icon flex-shrink-0"
          aria-label="Copy redirect URI"
          title="Copy redirect URI"
        >
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </button>
      </div>
    </div>
  );
}
