// ui/features/step-config/sections/WebhookWaitEditor.tsx

'use client';

import React, { useState, useMemo, useCallback } from 'react';
import { Copy, RefreshCw, Link, Clock, CheckCircle, AlertCircle, Eye, EyeOff } from 'lucide-react';
import { TIMEOUTS } from '@/shared/lib/constants';

interface WebhookWaitEditorProps {
  workflowId: string;
  stepId: string;
  parameters: Record<string, any>;
  onParametersChange: (parameters: Record<string, any>) => void;
}

// Generate a secure random token (client-side)
function generateSecureToken(length: number = 32): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('').slice(0, length);
}

export default function WebhookWaitEditor({
  workflowId,
  stepId,
  parameters,
  onParametersChange,
}: WebhookWaitEditorProps) {
  const [copied, setCopied] = useState(false);
  const [showAuthValue, setShowAuthValue] = useState(false);
  const [showRegenerateConfirm, setShowRegenerateConfirm] = useState(false);

  // Get values from parameters
  const webhookToken = parameters?.webhook_token || null;
  const authType = parameters?.webhook_auth_type || 'none';
  const authHeaderValue = parameters?.webhook_auth_header_value || '';
  const jwtSecret = parameters?.webhook_jwt_secret || '';

  // Build the full webhook URL
  const webhookUrl = useMemo(() => {
    if (!webhookToken) return null;
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    return `${baseUrl}/api/v1/webhooks/incoming/${webhookToken}`;
  }, [webhookToken]);

  // Generate new token
  const handleGenerate = useCallback(() => {
    onParametersChange({
      ...parameters,
      webhook_token: generateSecureToken(32),
    });
  }, [parameters, onParametersChange]);

  // Regenerate token
  const handleRegenerate = useCallback(() => {
    onParametersChange({
      ...parameters,
      webhook_token: generateSecureToken(32),
    });
    setShowRegenerateConfirm(false);
  }, [parameters, onParametersChange]);

  // Copy URL to clipboard
  const handleCopy = useCallback(async () => {
    if (!webhookUrl) return;
    try {
      await navigator.clipboard.writeText(webhookUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), TIMEOUTS.COPY_FEEDBACK);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }, [webhookUrl]);

  // Handle auth type change
  const handleAuthTypeChange = (newAuthType: string) => {
    onParametersChange({
      ...parameters,
      webhook_auth_type: newAuthType,
      // Clear auth values when switching types
      webhook_auth_header_value: newAuthType === 'header' ? authHeaderValue : undefined,
      webhook_jwt_secret: newAuthType === 'jwt' ? jwtSecret : undefined,
    });
  };

  // Handle auth value change
  const handleAuthValueChange = (value: string) => {
    if (authType === 'header') {
      onParametersChange({
        ...parameters,
        webhook_auth_header_value: value,
      });
    } else if (authType === 'jwt') {
      onParametersChange({
        ...parameters,
        webhook_jwt_secret: value,
      });
    }
  };

  // Generate auth secret
  const handleGenerateAuthSecret = () => {
    const secret = generateSecureToken(32);
    if (authType === 'header') {
      onParametersChange({
        ...parameters,
        webhook_auth_header_value: secret,
      });
    } else if (authType === 'jwt') {
      onParametersChange({
        ...parameters,
        webhook_jwt_secret: secret,
      });
    }
  };

  // Handle timeout change
  const handleTimeoutChange = (value: number) => {
    onParametersChange({
      ...parameters,
      timeout_seconds: value,
    });
  };

  // Handle expected fields change
  const handleExpectedFieldsChange = (value: string) => {
    const fields = value.split(',').map(f => f.trim()).filter(Boolean);
    onParametersChange({
      ...parameters,
      expected_fields: fields,
    });
  };

  const currentAuthValue = authType === 'header' ? authHeaderValue : authType === 'jwt' ? jwtSecret : '';

  return (
    <div className="space-y-6">
      {/* Webhook URL Section */}
      <div className="bg-card rounded-lg border border-info p-4">
        <div className="flex items-center gap-2 mb-3">
          <Link className="text-info" size={18} />
          <h4 className="text-sm font-semibold text-primary">
            Callback URL
          </h4>
        </div>

        {webhookUrl ? (
          <div className="space-y-3">
            {/* URL Display */}
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs bg-card text-primary p-2 rounded border border-primary overflow-x-auto break-all">
                {webhookUrl}
              </code>
              <button
                onClick={handleCopy}
                className="flex-shrink-0 p-2 rounded-md bg-info-subtle text-info hover:opacity-80 transition-colors"
                title="Copy URL"
              >
                {copied ? <CheckCircle size={16} /> : <Copy size={16} />}
              </button>
            </div>

            {/* Authentication */}
            <div className="flex items-center gap-2 flex-wrap">
              <label className="text-xs text-secondary flex-shrink-0">Auth:</label>
              <select
                value={authType}
                onChange={(e) => handleAuthTypeChange(e.target.value)}
                className="form-select text-xs py-1 px-1.5 w-32 flex-shrink-0"
              >
                <option value="none">None</option>
                <option value="header">Header Auth</option>
                <option value="jwt">JWT Auth</option>
              </select>

              {authType === 'header' && (
                <>
                  <span className="text-xs text-secondary font-mono flex-shrink-0">X-API-Key:</span>
                  <div className="relative flex-1 min-w-[150px]">
                    <input
                      type={showAuthValue ? 'text' : 'password'}
                      value={authHeaderValue}
                      onChange={(e) => handleAuthValueChange(e.target.value)}
                      placeholder="API key value"
                      className="form-input text-xs py-1 px-2 pr-8 w-full font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowAuthValue(!showAuthValue)}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted hover:text-secondary"
                    >
                      {showAuthValue ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={handleGenerateAuthSecret}
                    className="btn-secondary text-xs px-2 py-1 flex-shrink-0"
                  >
                    Generate
                  </button>
                </>
              )}

              {authType === 'jwt' && (
                <>
                  <div className="relative flex-1 min-w-[150px]">
                    <input
                      type={showAuthValue ? 'text' : 'password'}
                      value={jwtSecret}
                      onChange={(e) => handleAuthValueChange(e.target.value)}
                      placeholder="JWT signing secret"
                      className="form-input text-xs py-1 px-2 pr-8 w-full font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowAuthValue(!showAuthValue)}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted hover:text-secondary"
                    >
                      {showAuthValue ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={handleGenerateAuthSecret}
                    className="btn-secondary text-xs px-2 py-1 flex-shrink-0"
                  >
                    Generate
                  </button>
                </>
              )}
            </div>

            {authType === 'jwt' && (
              <p className="text-muted text-xs">
                <span className="font-medium text-secondary">Algorithm: HS256</span> (HMAC with SHA-256).
                Callers must send <code className="bg-card px-1 rounded">Authorization: Bearer &lt;jwt&gt;</code> signed with this secret.
              </p>
            )}

            {/* Regenerate Button */}
            {!showRegenerateConfirm ? (
              <button
                onClick={() => setShowRegenerateConfirm(true)}
                className="text-xs text-critical hover:opacity-80 flex items-center gap-1"
              >
                <RefreshCw size={12} />
                Regenerate URL
              </button>
            ) : (
              <div className="bg-critical-subtle border border-critical rounded-md p-3">
                <div className="flex items-start gap-2">
                  <AlertCircle className="text-critical flex-shrink-0 mt-0.5" size={16} />
                  <div className="flex-1">
                    <p className="text-sm text-critical font-medium">
                      Regenerate callback URL?
                    </p>
                    <p className="text-xs text-critical mt-1">
                      This will invalidate the current URL. Any external systems using the old URL will stop working.
                    </p>
                    <div className="flex gap-2 mt-2">
                      <button
                        onClick={handleRegenerate}
                        className="px-3 py-1 text-xs bg-critical text-white rounded hover:opacity-90"
                      >
                        Yes, Regenerate
                      </button>
                      <button
                        onClick={() => setShowRegenerateConfirm(false)}
                        className="px-3 py-1 text-xs bg-input text-secondary rounded hover:bg-surface"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <p className="text-muted text-xs">
              External systems should POST to this URL to resume the workflow at this step.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-secondary">
              Generate a callback URL to allow external systems to resume this workflow.
            </p>
            <button
              onClick={handleGenerate}
              className="btn-primary text-sm flex items-center gap-2"
            >
              <Link size={14} />
              Generate Callback URL
            </button>
          </div>
        )}
      </div>

      {/* Configuration Section */}
      <div className="space-y-4">
        {/* Timeout */}
        <div>
          <label className="flex items-center gap-2 text-sm font-medium text-secondary mb-1">
            <Clock size={14} />
            Timeout (seconds)
          </label>
          <input
            type="number"
            value={parameters?.timeout_seconds ?? 300}
            onChange={(e) => handleTimeoutChange(parseInt(e.target.value) || 0)}
            className="block w-full border border-primary rounded-md shadow-sm p-2 bg-card text-primary"
            min={0}
            max={86400}
          />
          <p className="mt-1 text-xs text-secondary">
            Maximum time to wait for callback (0 = no timeout, max 86400 = 24 hours)
          </p>
        </div>

        {/* Expected Fields */}
        <div>
          <label className="block text-sm font-medium text-secondary mb-1">
            Expected Fields (optional)
          </label>
          <input
            type="text"
            value={(parameters?.expected_fields || []).join(', ')}
            onChange={(e) => handleExpectedFieldsChange(e.target.value)}
            className="block w-full border border-primary rounded-md shadow-sm p-2 bg-card text-primary"
            placeholder="status, result, data"
          />
          <p className="mt-1 text-xs text-secondary">
            Comma-separated list of fields expected in the callback payload
          </p>
        </div>
      </div>

      {/* Info Box */}
      <div className="bg-info-subtle border border-info rounded-md p-3">
        <h5 className="text-sm font-medium text-info mb-2">
          How it works
        </h5>
        <ol className="text-xs text-info space-y-1 list-decimal list-inside">
          <li>When the workflow reaches this step, it pauses and waits</li>
          <li>An external system calls the callback URL with data</li>
          <li>The workflow resumes with the callback payload available to subsequent steps</li>
        </ol>
      </div>
    </div>
  );
}
