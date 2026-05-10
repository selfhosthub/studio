// ui/app/workflows/[id]/edit/components/WebhookAuthHelpModal.tsx

'use client';

import React from 'react';
import { Modal } from '@/shared/ui';

interface WebhookAuthHelpModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function WebhookAuthHelpModal({ isOpen, onClose }: WebhookAuthHelpModalProps) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Webhook Authentication" size="md">
      <div className="p-6 max-h-[70vh] overflow-y-auto">
        <div className="space-y-4 text-sm text-secondary">
          <p>Choose how external systems authenticate when calling your webhook.</p>

          <div className="border-l-2 border-primary pl-3">
            <h4 className="font-medium text-primary mb-1">None</h4>
            <p>No authentication required. Anyone with the webhook URL can trigger the workflow.</p>
          </div>

          <div className="border-l-2 border-info pl-3">
            <h4 className="font-medium text-primary mb-1">API Key Header</h4>
            <p className="mb-1">Callers must include a static API key in the request header:</p>
            <code className="bg-card px-2 py-1 rounded text-xs block">X-API-Key: your-api-key</code>
          </div>

          <div className="border-l-2 border-purple-400 pl-3"> {/* css-check-ignore: no semantic token */}
            <h4 className="font-medium text-primary mb-1">JWT Token</h4>
            <p className="mb-1">Callers must include a signed JWT in the Authorization header:</p>
            <code className="bg-card px-2 py-1 rounded text-xs block">Authorization: Bearer &lt;jwt&gt;</code>
            <p className="mt-1 text-xs">Uses HS256 algorithm. Good for machine-to-machine auth with expiring tokens.</p>
          </div>

          <div className="border-l-2 border-success pl-3">
            <h4 className="font-medium text-primary mb-1">HMAC Signature</h4>
            <p className="mb-1">Callers sign the request body and include the signature in a header:</p>
            <code className="bg-card px-2 py-1 rounded text-xs block">X-Hub-Signature-256: sha256=...</code>
            <p className="mt-1 text-xs">Common standard for webhook providers. Verifies payload integrity.</p>
          </div>

          <div className="bg-info-subtle border border-info rounded p-3">
            <h4 className="font-medium text-info mb-1">Which should I use?</h4>
            <ul className="list-disc list-inside space-y-1 text-info text-xs">
              <li><strong>Simple integrations:</strong> API Key Header</li>
              <li><strong>External webhooks:</strong> HMAC Signature</li>
              <li><strong>Custom services with expiring tokens:</strong> JWT Token</li>
            </ul>
          </div>
        </div>

        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="btn-primary text-sm"
          >
            Got it
          </button>
        </div>
      </div>
    </Modal>
  );
}
