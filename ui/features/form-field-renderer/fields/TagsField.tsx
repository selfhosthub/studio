// ui/features/form-field-renderer/fields/TagsField.tsx

'use client';

import React from 'react';
import type { FormFieldConfig } from '@/entities/workflow';
import { TagsInput } from '@/features/step-config/MappableParameterField/components/TagsInput';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: (string | number)[]) => void;
  paramKey?: string;
}

export function TagsField({ config, value, onChange, paramKey }: Props) {
  const itemType: 'string' | 'integer' | 'number' =
    config.itemType === 'integer' || config.itemType === 'number'
      ? (config.itemType as 'integer' | 'number')
      : 'string';
  return (
    <TagsInput
      value={Array.isArray(value) ? (value as (string | number)[]) : []}
      itemType={itemType}
      placeholder={config.placeholder ?? ''}
      paramKey={paramKey ?? ''}
      onChange={(_k, next) => onChange(next)}
    />
  );
}
