// ui/features/form-field-renderer/fields/DateField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: string) => void;
  error?: string;
}

export function DateField({ config, value, onChange, error }: Props) {
  const errorClass = error ? ' border-danger' : '';
  return (
    <input
      type="date"
      className={`form-input${errorClass}`}
      value={(value as string | undefined) ?? ''}
      onChange={(e) => onChange(e.target.value)}
      required={config.required}
    />
  );
}
