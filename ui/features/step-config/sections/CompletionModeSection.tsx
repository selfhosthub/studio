// ui/features/step-config/sections/CompletionModeSection.tsx

'use client';

import Link from 'next/link';
import { STEP_CONFIG_DEFAULTS } from '@/shared/defaults';

/**
 * The `completion_modes` member that turns on provider callbacks (vs synchronous
 * `get` polling). Mirrors `contracts/webhook_completion.py::WEBHOOK_MODE` - keep
 * the two in sync.
 */
export const WEBHOOK_MODE = 'webhook';

/** Display labels for known completion modes; unknown modes fall back to their slug. */
export const COMPLETION_MODE_LABELS: Record<string, string> = {
  get: 'Poll for result (synchronous)',
  webhook: 'Wait for provider callback (webhook)',
};

interface CompletionModeSectionProps {
  /** The selected service's client_metadata; gates on completion_modes. */
  serviceMetadata?: Record<string, any> | null;
  /** Provider of the step's selected credential, for the credential-page jump-link. */
  credentialProviderId?: string;
  /**
   * Whether the step's selected credential holds a webhook_callback_api_key.
   * undefined => unknown (no credential selected yet); false => selected but missing.
   */
  credentialHasWebhookKey?: boolean;
  completionMode?: string;
  onCompletionModeChange: (mode: string) => void;
  title?: string;
}

/**
 * Per-step async completion mode (get | webhook), shown only for services that
 * declare webhook support. The webhook binding lives on the CREDENTIAL (one
 * callback URL per provider API key, demuxed by generation id), so there is no
 * per-step credential assignment here - just the mode choice. In webhook mode,
 * if the selected credential lacks a callback key we warn + link to the
 * credential page where the key and callback URL are configured.
 */
export default function CompletionModeSection({
  serviceMetadata,
  credentialProviderId,
  credentialHasWebhookKey,
  completionMode,
  onCompletionModeChange,
  title = 'Completion Mode',
}: CompletionModeSectionProps) {
  const declaredModes = serviceMetadata?.completion_modes;
  const modes: string[] = Array.isArray(declaredModes) ? declaredModes : [];
  const supportsWebhook = modes.includes(WEBHOOK_MODE);

  const mode = completionMode || STEP_CONFIG_DEFAULTS.completionMode;
  const isWebhook = mode === WEBHOOK_MODE;

  if (!supportsWebhook) return null;

  // execution_token routing self-routes by a per-render callback token minted at
  // run time (json2video) - no credential callback key exists, so the
  // missing-key warning never applies.
  const tokenRouted =
    serviceMetadata?.webhook_completion?.routing === 'execution_token';

  // Warn only on the precise misconfiguration: webhook mode + a selected
  // credential that has no callback key. Unknown (no credential) stays quiet.
  const showMissingKeyWarning =
    isWebhook && !tokenRouted && credentialHasWebhookKey === false;

  return (
    <div className="mb-4 p-3 bg-info-subtle border border-info rounded-md" data-testid="step-completion-mode">
      <label htmlFor="completion-mode" className="block text-sm font-medium mb-1">
        {title}
      </label>
      <select
        id="completion-mode"
        value={mode}
        onChange={(e) => onCompletionModeChange(e.target.value)}
        className="w-full p-2 border rounded text-sm"
      >
        {modes.map((m) => (
          <option key={m} value={m}>
            {COMPLETION_MODE_LABELS[m] ?? m}
          </option>
        ))}
      </select>

      {showMissingKeyWarning && (
        <p className="mt-2 text-xs text-warning">
          The selected credential has no webhook callback key.{' '}
          {credentialProviderId ? (
            <Link
              href={`/providers/${credentialProviderId}/credentials`}
              className="underline hover:opacity-80"
            >
              Configure it on the credential page
            </Link>
          ) : (
            'Configure it on the credential page'
          )}{' '}
          to receive provider callbacks.
        </p>
      )}
    </div>
  );
}
