// ui/app/workflows/components/JsonParseModal.tsx

'use client';

import React, { useState } from 'react';
import { Modal } from '@/shared/ui';

interface JsonParseModalProps {
  type: 'input' | 'output';
  onClose: () => void;
  onParse: (parsed: Record<string, unknown>) => void;
}

/**
 * Recursively parse JSON and create output fields with nested paths.
 */
export function parseJsonToOutputFields(
  json: unknown,
  prefix: string = '',
  maxDepth: number = 3,
  currentDepth: number = 0
): Record<string, unknown> {
  const detectedOutputs: Record<string, unknown> = {};

  if (!json || currentDepth > maxDepth) return detectedOutputs;

  if (typeof json === 'object' && !Array.isArray(json)) {
    Object.keys(json as Record<string, unknown>).forEach((key) => {
      const value = (json as Record<string, unknown>)[key];
      const path = prefix ? `${prefix}.${key}` : key;
      const safeFieldName = path.replace(/\./g, '_');

      detectedOutputs[safeFieldName] = {
        path,
        description: `${key} field`,
        type: Array.isArray(value) ? 'array' : typeof value,
      };

      if (typeof value === 'object' && value !== null && currentDepth < maxDepth) {
        const nestedOutputs = parseJsonToOutputFields(
          value,
          path,
          maxDepth,
          currentDepth + 1
        );
        Object.assign(detectedOutputs, nestedOutputs);
      }
    });
  } else if (Array.isArray(json) && json.length > 0 && currentDepth < maxDepth) {
    const safeFieldName = prefix.replace(/\./g, '_') || 'items';
    detectedOutputs[safeFieldName] = {
      path: prefix || 'items',
      description: `${prefix || 'Items'} array`,
      type: 'array',
    };

    if (typeof json[0] === 'object' && json[0] !== null) {
      const itemPrefix = prefix ? `${prefix}[0]` : '[0]';
      const nestedOutputs = parseJsonToOutputFields(
        json[0],
        itemPrefix,
        maxDepth,
        currentDepth + 1
      );
      Object.assign(detectedOutputs, nestedOutputs);
    }
  }

  return detectedOutputs;
}

export function JsonParseModal({ type, onClose, onParse }: JsonParseModalProps) {
  const [jsonText, setJsonText] = useState('');
  const [jsonParseError, setJsonParseError] = useState('');

  const handleParse = () => {
    try {
      const parsedJson = JSON.parse(jsonText);

      if (type === 'output') {
        const detectedOutputs = parseJsonToOutputFields(parsedJson);
        onParse(detectedOutputs);
      } else {
        onParse(parsedJson);
      }

      onClose();
      setJsonParseError('');
    } catch {
      setJsonParseError('Invalid JSON format');
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title={`Parse JSON ${type === 'output' ? 'Response' : 'Input'}`} size="sm">
      <div className="p-6">
        <div className="mb-4">
          <label className="block text-sm font-medium text-secondary mb-1">
            Paste JSON here:
          </label>
          <textarea
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            rows={8}
            className="block w-full border border-primary rounded-md shadow-sm p-2 font-mono text-sm"
          />

          {jsonParseError && (
            <p className="mt-2 text-sm text-danger">{jsonParseError}</p>
          )}
        </div>

        <div className="flex justify-end space-x-2">
          <button
            onClick={onClose}
            className="btn-danger text-sm"
          >
            Cancel
          </button>

          <button
            onClick={handleParse}
            className="btn-primary text-sm"
          >
            Parse
          </button>
        </div>
      </div>
    </Modal>
  );
}
