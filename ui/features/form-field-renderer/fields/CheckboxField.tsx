// ui/features/form-field-renderer/fields/CheckboxField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: boolean) => void;
}

export function CheckboxField({ config, value, onChange }: Props) {
  return (
    <div className="flex items-center">
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-primary text-info focus:ring-blue-500"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
      {config.description && (
        <span className="ml-2 text-sm text-secondary">{config.description}</span>
      )}
    </div>
  );
}
