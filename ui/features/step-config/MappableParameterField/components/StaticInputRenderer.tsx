// ui/features/step-config/MappableParameterField/components/StaticInputRenderer.tsx

'use client';

import React from 'react';
import { Step } from '@/entities/workflow';
import DynamicCombobox from '@/shared/ui/DynamicCombobox';
import { DateTimePickerModal } from './DateTimePickerModal';
import { ResolutionPicker } from './ResolutionPicker';
import { FieldInput } from './FieldInput';
import type { PropertySchema } from '../types';

interface StaticInputRendererProps {
  schema: PropertySchema;
  value: any;
  paramKey: string;
  label: string;
  onValueChange: (key: string, value: any) => void;
  allFieldValues?: Record<string, any>;
  exampleValue?: any;
  providerId?: string;
  credentialId?: string;
  required?: boolean;
  previousSteps: Step[];
}

export function StaticInputRenderer({
  schema,
  value,
  paramKey,
  label,
  onValueChange,
  allFieldValues,
  exampleValue,
  providerId,
  credentialId,
  required = false,
  previousSteps,
}: StaticInputRendererProps) {
  const handleChange = (next: any) => onValueChange(paramKey, next);

  if (schema.ui?.widget === 'resolution-picker') {
    return (
      <ResolutionPicker
        width={value ?? schema.default ?? 1920}
        height={allFieldValues?.height ?? 1080}
        onWidthChange={(w) => onValueChange(paramKey, w)}
        onHeightChange={(h) => onValueChange('height', h)}
        minValue={schema.minimum}
        maxValue={schema.maximum}
      />
    );
  }

  if (schema.format === 'date' || schema.format === 'date-time') {
    return (
      <DateTimePickerModal
        value={value ?? schema.default ?? ''}
        onChange={handleChange}
        format={schema.format}
        placeholder={schema.ui?.placeholder}
      />
    );
  }

  if (schema.dynamicOptions && providerId) {
    const placeholderText = exampleValue !== undefined
      ? `e.g. ${typeof exampleValue === 'string' ? exampleValue : JSON.stringify(exampleValue)}`
      : schema.ui?.placeholder || `Select or enter ${schema.title || paramKey}...`;
    return (
      <DynamicCombobox
        id={paramKey}
        value={value ?? ''}
        onChange={handleChange}
        dynamicOptions={schema.dynamicOptions}
        providerId={providerId}
        credentialId={credentialId}
        formData={allFieldValues || {}}
        required={required}
        placeholder={placeholderText}
        className="flex-1"
        previousSteps={previousSteps}
      />
    );
  }

  return (
    <FieldInput
      schema={schema}
      value={value}
      onChange={handleChange}
      size="default"
      paramKey={paramKey}
      label={label}
      required={required}
    />
  );
}
