// ui/features/form-field-renderer/fields/FileField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: File | null) => void;
  error?: string;
}

export function FileField({ config, onChange, error }: Props) {
  const errorClass = error ? ' border-danger' : '';
  const accept = config.acceptedFileTypes?.join(',');
  return (
    <input
      type="file"
      className={`form-input${errorClass}`}
      accept={accept}
      required={config.required}
      onChange={(e) => onChange(e.target.files?.[0] ?? null)}
    />
  );
}
