// ui/app/workflows/[id]/edit/components/CredentialBanner.tsx

'use client';

import React from 'react';
import Link from 'next/link';
import { CredentialCheckResponse } from '@/shared/api';

interface CredentialBannerProps {
  credentialCheck: CredentialCheckResponse | null;
  credentialCheckLoading: boolean;
  onSelectStep: (stepId: string) => void;
}

export function CredentialBanner({ credentialCheck, credentialCheckLoading, onSelectStep }: CredentialBannerProps) {
  if (credentialCheckLoading || !credentialCheck || credentialCheck.ready) {
    return null;
  }

  const providerIssues = credentialCheck.issues.filter(i => i.status === 'provider_not_installed');
  const promptIssues = credentialCheck.issues.filter(i => i.status === 'prompt_missing');
  const credentialIssues = credentialCheck.issues.filter(i => i.status !== 'provider_not_installed' && i.status !== 'prompt_missing');

  const title =
    providerIssues.length > 0 && credentialIssues.length === 0 && promptIssues.length === 0
      ? 'Provider Setup Required'
      : promptIssues.length > 0 && credentialIssues.length === 0 && providerIssues.length === 0
        ? 'AI Agent Prompt Setup Required'
        : 'Setup Required';

  return (
    <div className="mb-3 alert alert-warning">
      <div className="flex items-start">
        <div className="flex-shrink-0">
          <svg className="h-5 w-5 text-warning" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
          </svg>
        </div>
        <div className="ml-3 flex-1">
          <h3 className="text-sm font-medium alert-warning-text">
            {title}
          </h3>
          <p className="mt-1 text-sm alert-warning-text">
            This workflow cannot run until the following issues are resolved:
          </p>
          <ul className="mt-2 text-sm alert-warning-text list-disc list-inside space-y-1">
            {providerIssues.map((issue, index) => (
              <li key={`provider-${index}`}>
                <span className="font-medium">{issue.step_name}</span>: {issue.message}
                <Link
                  href={issue.action_url}
                  className="ml-2 underline hover:no-underline"
                >
                  Install →
                </Link>
              </li>
            ))}
            {promptIssues.map((issue, index) => (
              <li key={`prompt-${index}`}>
                <span className="font-medium">{issue.step_name}</span>: {issue.message}
                {issue.action_url.includes('/marketplace') ? (
                  <Link
                    href={issue.action_url}
                    className="ml-2 underline hover:no-underline"
                  >
                    Install →
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => onSelectStep(issue.step_id)}
                    className="ml-2 underline hover:no-underline"
                  >
                    Configure →
                  </button>
                )}
              </li>
            ))}
            {credentialIssues.map((issue, index) => (
              <li key={`credential-${index}`}>
                <span className="font-medium">{issue.step_name}</span>: {issue.message}
                <button
                  type="button"
                  onClick={() => onSelectStep(issue.step_id)}
                  className="ml-2 underline hover:no-underline"
                >
                  Configure →
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
