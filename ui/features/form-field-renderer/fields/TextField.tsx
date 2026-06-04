// ui/features/form-field-renderer/fields/TextField.tsx

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

export function TextField({ config, value, onChange, error, autoFocus }: Props) {
  const errorClass = error ? ' border-danger' : '';
  return (
    <input
      type="text"
      className={`form-input${errorClass}`}
      value={(value as string | undefined) ?? ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={config.placeholder}
      required={config.required}
      minLength={config.minLength}
      maxLength={config.maxLength}
      autoFocus={autoFocus}
    />
  );
}
