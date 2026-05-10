// ui/features/form-field-renderer/fields/NumberField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: number | '') => void;
  error?: string;
  autoFocus?: boolean;
}

export function NumberField({ config, value, onChange, error, autoFocus }: Props) {
  const errorClass = error ? ' border-danger' : '';
  return (
    <input
      type="number"
      className={`form-input${errorClass}`}
      value={(value as number | string | undefined) ?? ''}
      onChange={(e) => {
        const raw = e.target.value;
        if (raw === '') {
          onChange('');
          return;
        }
        const n = parseFloat(raw);
        onChange(isNaN(n) ? '' : n);
      }}
      placeholder={config.placeholder}
      required={config.required}
      min={config.min}
      max={config.max}
      step="any"
      autoFocus={autoFocus}
    />
  );
}
