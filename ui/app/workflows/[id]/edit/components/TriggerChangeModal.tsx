// ui/app/workflows/[id]/edit/components/TriggerChangeModal.tsx

'use client';

import React from 'react';
import { Modal } from '@/shared/ui';

interface TriggerChangeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function TriggerChangeModal({ isOpen, onClose, onConfirm }: TriggerChangeModalProps) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Change Trigger Type?" size="sm">
      <div className="p-6">
        <p className="text-sm text-secondary mb-4">
          This will delete the webhook URL. Any external systems using this URL will no longer be able to trigger this workflow.
        </p>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="btn-secondary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="btn-danger"
          >
            Delete Webhook & Change
          </button>
        </div>
      </div>
    </Modal>
  );
}

