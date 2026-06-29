// ui/features/form-field-renderer/fields/TextareaField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: string) => void;
  error?: string;
  autoFocus?: boolean;
}

export function TextareaField({ config, value, onChange, error, autoFocus }: Props) {
  const errorClass = error ? ' border-danger' : '';
  return (
    <textarea
      className={`form-input${errorClass}`}
      rows={4}
      value={(value as string | undefined) ?? ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={config.placeholder}
      required={config.required}
      autoFocus={autoFocus}
    />
  );
}
