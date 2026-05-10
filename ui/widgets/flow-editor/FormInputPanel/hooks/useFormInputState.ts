// ui/widgets/flow-editor/FormInputPanel/hooks/useFormInputState.ts

import { useState, useEffect, Dispatch, SetStateAction } from 'react';
import { WorkflowFormSchema, FormFieldConfig } from '@/entities/workflow';

/** Normalize config from API (snake_case) to frontend (camelCase) format */
export function normalizeFormFieldConfig(config: any): FormFieldConfig {
  return {
    label: config.label,
    placeholder: config.placeholder,
    description: config.description,
    required: config.required,
    fieldType: (config.fieldType || config.field_type || 'text') as FormFieldConfig['fieldType'],
    defaultValue: config.defaultValue ?? config.default_value,
    options: config.options,
    minLength: config.minLength ?? config.min_length,
    maxLength: config.maxLength ?? config.max_length,
    min: config.min,
    max: config.max,
    acceptedFileTypes: config.acceptedFileTypes ?? config.accepted_file_types,
    maxFileSizeMB: config.maxFileSizeMB ?? config.max_file_size_mb,
    size: config.size,
  };
}

/** Returns the CSS grid column class for a field based on its type and size config */
export function getFormFieldSizeClass(config: FormFieldConfig): string {
  if (config.fieldType === 'textarea' || config.fieldType === 'json') {
    return 'col-span-full';
  }
  switch (config.size) {
    case 'small':
      return 'col-span-1';
    case 'medium':
      return 'col-span-1 lg:col-span-1';
    case 'large':
      return 'col-span-full lg:col-span-1';
    case 'full':
      return 'col-span-full';
    default:
      if (['text', 'number', 'select', 'date', 'datetime'].includes(config.fieldType || 'text')) {
        return 'col-span-1';
      }
      return 'col-span-full';
  }
}

export interface UseFormInputStateReturn {
  formValues: Record<string, any>;
  jsonModeFields: Set<string>;
  updateValue: (stepId: string, paramKey: string, value: any) => void;
  toggleJsonMode: (key: string) => void;
  clearError: (key: string) => void;
  setFormValues: Dispatch<SetStateAction<Record<string, any>>>;
}

/**
 * Manages form values state and JSON mode toggles for FormInputPanel.
 * Initializes values from schema defaults or provided initialValues.
 */
export function useFormInputState(
  formSchema: WorkflowFormSchema,
  initialValues?: Record<string, any>,
  onErrorClear?: (key: string) => void,
): UseFormInputStateReturn {
  const [formValues, setFormValues] = useState<Record<string, any>>({});
  const [jsonModeFields, setJsonModeFields] = useState<Set<string>>(new Set());

  useEffect(() => {
    const values: Record<string, any> = {};
    formSchema.fields.forEach((field) => {
      const key = `${field.step_id}.${field.parameter_key}`;
      const config = normalizeFormFieldConfig(field.config);
      if (initialValues?.[key] !== undefined) {
        values[key] = initialValues[key];
      } else if (config.defaultValue !== undefined) {
        values[key] = config.defaultValue;
      } else if (config.fieldType === 'checkbox') {
        values[key] = false;
      } else if (config.fieldType === 'multiselect') {
        values[key] = [];
      } else {
        values[key] = '';
      }
    });
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFormValues(values);
  }, [formSchema, initialValues]);

  const updateValue = (stepId: string, paramKey: string, value: any) => {
    const key = `${stepId}.${paramKey}`;
    setFormValues((prev) => ({ ...prev, [key]: value }));
    onErrorClear?.(key);
  };

  const toggleJsonMode = (key: string) => {
    setJsonModeFields((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const clearError = (key: string) => {
    onErrorClear?.(key);
  };

  return { formValues, jsonModeFields, updateValue, toggleJsonMode, clearError, setFormValues };
}
