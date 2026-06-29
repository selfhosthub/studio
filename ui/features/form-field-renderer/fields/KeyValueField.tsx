// ui/features/form-field-renderer/fields/KeyValueField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';
import { KeyValueEditor } from '@/features/step-config/MappableParameterField/components/KeyValueEditor';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: Record<string, string>) => void;
}

export function KeyValueField({ config, value, onChange }: Props) {
  const dict =
    value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, string>)
      : {};
  return (
    <KeyValueEditor
      value={dict}
      onChange={onChange}
      keyPlaceholder={config.keyPlaceholder}
      valuePlaceholder={config.valuePlaceholder}
      addLabel={config.addLabel}
    />
  );
}
