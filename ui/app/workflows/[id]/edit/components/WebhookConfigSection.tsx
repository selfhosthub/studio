// ui/app/workflows/[id]/edit/components/WebhookConfigSection.tsx

'use client';

import React from 'react';
import { Copy, Check, RefreshCw } from 'lucide-react';
import { Eye, EyeOff, HelpCircle } from 'lucide-react';
import { TIMEOUTS } from '@/shared/lib/constants';

interface WebhookConfigSectionProps {
  webhook: {
    webhookMethod: 'POST' | 'GET';
    setWebhookMethod: (m: 'POST' | 'GET') => void;
    webhookUrl: string;
    webhookTokenLoading: boolean;
    handleCopyWebhookUrl: () => void;
    copiedWebhookUrl: boolean;
    handleCopyCurlCommand: () => void;
    copiedCurlCommand: boolean;
    webhookAuthType: 'none' | 'header' | 'jwt' | 'hmac';
    setWebhookAuthType: (t: 'none' | 'header' | 'jwt' | 'hmac') => void;
    webhookAuthHeaderValue: string;
    setWebhookAuthHeaderValue: (v: string) => void;
    webhookJwtSecret: string;
    setWebhookJwtSecret: (v: string) => void;
    showWebhookAuthValue: boolean;
    setShowWebhookAuthValue: (v: boolean) => void;
    generatingAuth: boolean;
    handleGenerateAuthToken: () => void;
    copiedSigningSecret: boolean;
    setCopiedSigningSecret: (v: boolean) => void;
    setShowHmacHelpModal: (v: boolean) => void;
  };
  webhookToken: string | null;
  webhookSecret: string | null;
  onMethodChange: (method: 'POST' | 'GET') => void;
  onRegenerateToken: () => void;
}

export function WebhookConfigSection({
  webhook,
  webhookToken,
  webhookSecret,
  onMethodChange,
  onRegenerateToken,
}: WebhookConfigSectionProps) {
  return (
    <div className="md:col-span-2 p-3 bg-surface rounded-md border border-primary">
      {(webhook.webhookTokenLoading || !webhookToken) ? (
        <div className="text-muted">Generating webhook URL...</div>
      ) : (
        <div className="space-y-3">
          {/* Method + URL + Copy + cURL buttons */}
          <div className="flex items-center gap-2 min-w-0">
            <select
              value={webhook.webhookMethod}
              onChange={(e) => onMethodChange(e.target.value as 'POST' | 'GET')}
              className="form-select text-xs py-1 px-1.5 !w-20 flex-shrink-0"
            >
              <option value="POST">POST</option>
              <option value="GET">GET</option>
            </select>
            <input
              type="text"
              readOnly
              value={webhook.webhookUrl}
              className="form-input-mono form-input-readonly flex-1 min-w-0 text-xs py-1.5"
            />
            <button
              type="button"
              onClick={webhook.handleCopyWebhookUrl}
              className="btn-secondary btn-with-icon p-1.5 flex-shrink-0"
              title="Copy URL"
            >
              {webhook.copiedWebhookUrl ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />}
            </button>
            <button
              type="button"
              onClick={webhook.handleCopyCurlCommand}
              className="btn-secondary text-xs px-2 py-1.5 flex-shrink-0"
              title="Copy cURL command"
            >
              {webhook.copiedCurlCommand ? <Check className="h-4 w-4 text-success" /> : 'cURL'}
            </button>
          </div>

          {/* Authentication row */}
          <div className="flex items-center gap-2 min-w-0 flex-wrap">
            <label className="text-xs text-secondary flex-shrink-0 flex items-center gap-1">
              Auth:
              <button
                type="button"
                onClick={() => webhook.setShowHmacHelpModal(true)}
                className="text-muted hover:text-info"
                title="Learn about authentication options"
              >
                <HelpCircle className="h-3.5 w-3.5" />
              </button>
            </label>
            <select
              value={webhook.webhookAuthType}
              onChange={(e) => webhook.setWebhookAuthType(e.target.value as 'none' | 'header' | 'jwt' | 'hmac')}
              className="form-select text-xs py-1 px-1.5 !w-40 flex-shrink-0"
            >
              <option value="none">None</option>
              <option value="header">API Key Header</option>
              <option value="jwt">JWT Token</option>
              <option value="hmac">HMAC Signature</option>
            </select>

            {/* Header Auth fields */}
            {webhook.webhookAuthType === 'header' && (
              <>
                <span className="text-xs text-muted font-mono flex-shrink-0">X-API-Key:</span>
                <div className="relative flex-1 min-w-0">
                  <input
                    type={webhook.showWebhookAuthValue ? 'text' : 'password'}
                    value={webhook.webhookAuthHeaderValue}
                    onChange={(e) => webhook.setWebhookAuthHeaderValue(e.target.value)}
                    placeholder="API key value"
                    className="form-input text-xs py-1 px-2 pr-8 w-full font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => webhook.setShowWebhookAuthValue(!webhook.showWebhookAuthValue)}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 icon-muted"
                    title={webhook.showWebhookAuthValue ? 'Hide value' : 'Show value'}
                  >
                    {webhook.showWebhookAuthValue ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                </div>
                <button
                  type="button"
                  onClick={webhook.handleGenerateAuthToken}
                  disabled={webhook.generatingAuth}
                  className="btn-secondary text-xs px-2 py-1 flex-shrink-0"
                  title="Generate random API key"
                >
                  {webhook.generatingAuth ? '...' : 'Generate'}
                </button>
              </>
            )}

            {/* JWT Auth fields */}
            {webhook.webhookAuthType === 'jwt' && (
              <>
                <span className="text-xs text-muted font-mono flex-shrink-0">JWT Secret:</span>
                <div className="relative flex-1 min-w-0">
                  <input
                    type={webhook.showWebhookAuthValue ? 'text' : 'password'}
                    value={webhook.webhookJwtSecret}
                    onChange={(e) => webhook.setWebhookJwtSecret(e.target.value)}
                    placeholder="Secret for validating JWT tokens"
                    className="form-input text-xs py-1 px-2 pr-8 w-full font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => webhook.setShowWebhookAuthValue(!webhook.showWebhookAuthValue)}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 icon-muted"
                    title={webhook.showWebhookAuthValue ? 'Hide secret' : 'Show secret'}
                  >
                    {webhook.showWebhookAuthValue ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                </div>
                <button
                  type="button"
                  onClick={webhook.handleGenerateAuthToken}
                  disabled={webhook.generatingAuth}
                  className="btn-secondary text-xs px-2 py-1 flex-shrink-0"
                  title="Generate random secret"
                >
                  {webhook.generatingAuth ? '...' : 'Generate'}
                </button>
              </>
            )}

            {/* HMAC Signature fields */}
            {webhook.webhookAuthType === 'hmac' && webhookSecret && (
              <>
                <span className="text-xs text-muted font-mono flex-shrink-0">Secret:</span>
                <div className="relative flex-1 min-w-0">
                  <input
                    type={webhook.showWebhookAuthValue ? 'text' : 'password'}
                    readOnly
                    value={webhookSecret}
                    className="form-input-mono form-input-readonly text-xs py-1.5 pr-16 w-full"
                  />
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(webhookSecret);
                        webhook.setCopiedSigningSecret(true);
                        setTimeout(() => webhook.setCopiedSigningSecret(false), TIMEOUTS.COPY_FEEDBACK);
                      }}
                      className="p-1 icon-muted"
                      title="Copy HMAC secret"
                    >
                      {webhook.copiedSigningSecret ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => webhook.setShowWebhookAuthValue(!webhook.showWebhookAuthValue)}
                      className="p-1 icon-muted"
                      title={webhook.showWebhookAuthValue ? 'Hide secret' : 'Show secret'}
                    >
                      {webhook.showWebhookAuthValue ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* JWT Auth helper text */}
          {webhook.webhookAuthType === 'jwt' && (
            <p className="text-muted text-xs">
              <span className="font-medium text-secondary">Algorithm: HS256</span> (HMAC with SHA-256).
              Callers must send <code className="bg-surface px-1 rounded">Authorization: Bearer &lt;jwt&gt;</code> signed with this secret.
            </p>
          )}

          {/* HMAC Signature helper text */}
          {webhook.webhookAuthType === 'hmac' && (
            <p className="text-muted text-xs">
              Configure this secret in your external system.
              Requests must include <code className="bg-surface px-1 rounded">X-Hub-Signature-256</code> header with HMAC-SHA256 signature.
            </p>
          )}

          {/* Regenerate button */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onRegenerateToken}
              className="text-xs text-secondary hover:text-primary inline-flex items-center"
              disabled={webhook.webhookTokenLoading}
            >
              <RefreshCw className="h-3 w-3 mr-1" />
              Regenerate URL
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
