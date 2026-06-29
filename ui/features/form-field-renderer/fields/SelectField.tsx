// ui/features/form-field-renderer/fields/SelectField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: string) => void;
  error?: string;
}

export function SelectField({ config, value, onChange, error }: Props) {
  const errorClass = error ? ' border-danger' : '';
  return (
    <select
      className={`form-input${errorClass}`}
      value={(value as string | undefined) ?? ''}
      onChange={(e) => onChange(e.target.value)}
      required={config.required}
    >
      <option value="">Select...</option>
      {config.options?.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
