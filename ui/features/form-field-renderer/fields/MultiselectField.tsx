// ui/features/form-field-renderer/fields/MultiselectField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';
import { MultiselectInput } from '@/features/step-config/MappableParameterField/components/MultiselectInput';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: string[]) => void;
  paramKey?: string;
}

export function MultiselectField({ config, value, onChange, paramKey }: Props) {
  const schema = {
    type: 'array',
    items: {
      enum: config.options?.map((o) => o.value) ?? [],
      enumNames: config.options?.map((o) => o.label) ?? [],
    },
  };
  return (
    <MultiselectInput
      value={Array.isArray(value) ? (value as string[]) : []}
      schema={schema as any}
      paramKey={paramKey ?? ''}
      onValueChange={(_k, next) => onChange(next)}
    />
  );
}
