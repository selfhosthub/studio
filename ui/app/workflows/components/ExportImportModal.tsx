// ui/app/workflows/components/ExportImportModal.tsx

'use client';

import React, { useState } from 'react';
import { Modal } from '@/shared/ui';

interface ExportImportModalProps {
  type: 'input' | 'output';
  initialJson: string;
  onClose: () => void;
  onImport: (parsed: Record<string, unknown>) => void;
}

export function ExportImportModal({ type, initialJson, onClose, onImport }: ExportImportModalProps) {
  const [exportedJson, setExportedJson] = useState(initialJson);

  const handleImport = () => {
    try {
      const parsed = JSON.parse(exportedJson);
      onImport(parsed);
      onClose();
    } catch (err: unknown) {
      console.error('Failed to parse JSON for import:', err);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title={`Export/Import ${type === 'output' ? 'Output Fields' : 'Input Mappings'}`} size="sm">
      <div className="p-6">
        <div className="mb-4">
          <label className="block text-sm font-medium text-secondary mb-1">
            JSON:
          </label>
          <textarea
            value={exportedJson}
            onChange={(e) => setExportedJson(e.target.value)}
            rows={8}
            className="block w-full border border-primary rounded-md shadow-sm p-2 font-mono text-sm"
          />
        </div>

        <div className="flex justify-end space-x-2">
          <button
            onClick={onClose}
            className="btn-danger text-sm"
          >
            Cancel
          </button>

          <button
            onClick={handleImport}
            className="btn-primary text-sm"
          >
            Import
          </button>
        </div>
      </div>
    </Modal>
  );
}
