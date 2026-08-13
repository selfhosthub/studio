// ui/features/form-field-renderer/fields/ComboboxField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: string) => void;
  error?: string;
  autoFocus?: boolean;
  paramKey?: string;
}

export function ComboboxField({ config, value, onChange, error, autoFocus, paramKey }: Props) {
  const errorClass = error ? ' border-danger' : '';
  const listId = `combobox-options-${paramKey ?? ''}`;
  return (
    <>
      <input
        type="text"
        list={listId}
        className={`form-input${errorClass}`}
        value={(value as string | undefined) ?? ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={config.placeholder}
        required={config.required}
        autoFocus={autoFocus}
      />
      <datalist id={listId}>
        {config.options?.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </datalist>
    </>
  );
}
