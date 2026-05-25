// ui/widgets/flow-editor/FormInputPanel/components/FormFieldPreview.tsx

'use client';

import React from 'react';
import { FormField, FormFieldConfig } from '@/entities/workflow';
import { FormFieldRenderer } from '@/features/form-field-renderer';

interface FormFieldPreviewProps {
  field: FormField;
  config: FormFieldConfig;
  value: unknown;
  error?: string;
  onChange: (stepId: string, paramKey: string, value: unknown) => void;
}

/**
 * Author-facing preview of the runtime form field, shown in the flow
 * editor's FormInputPanel. Delegates to the shared FormFieldRenderer so
 * the preview never drifts from what end users actually see when the
 * workflow runs. The wrapper exists only to adapt the caller's
 * `(stepId, paramKey, value)` onChange signature to the renderer's
 * single-argument one.
 */
export function FormFieldPreview({
  field,
  config,
  value,
  error,
  onChange,
}: FormFieldPreviewProps) {
  const paramKey = `${field.step_id}.${field.parameter_key}`;
  return (
    <FormFieldRenderer
      config={config}
      value={value}
      onChange={(next) => onChange(field.step_id, field.parameter_key, next)}
      error={error}
      paramKey={paramKey}
    />
  );
}
