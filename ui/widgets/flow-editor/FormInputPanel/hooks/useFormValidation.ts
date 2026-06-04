// ui/widgets/flow-editor/FormInputPanel/hooks/useFormValidation.ts

import { useState, Dispatch, SetStateAction } from 'react';
import { WorkflowFormSchema } from '@/entities/workflow';
import { normalizeFormFieldConfig } from './useFormInputState';

export interface UseFormValidationReturn {
  errors: Record<string, string>;
  validate: (formValues: Record<string, any>) => boolean;
  clearError: (key: string) => void;
  setErrors: Dispatch<SetStateAction<Record<string, string>>>;
}

/**
 * Handles required, number (min/max), text length, and JSON validation.
 * Returns errors keyed by "{step_id}.{parameter_key}".
 */
export function useFormValidation(formSchema: WorkflowFormSchema): UseFormValidationReturn {
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (formValues: Record<string, any>): boolean => {
    const newErrors: Record<string, string> = {};
    let isValid = true;

    formSchema.fields.forEach((field) => {
      const key = `${field.step_id}.${field.parameter_key}`;
      const value = formValues[key];
      const config = normalizeFormFieldConfig(field.config);

      if (config.required) {
        if (value === undefined || value === null || value === '') {
          newErrors[key] = `${config.label} is required`;
          isValid = false;
        }
      }

      // Number validation
      if (config.fieldType === 'number' && value !== '' && value != null) {
        const numVal = Number(value);
        if (isNaN(numVal)) {
          newErrors[key] = 'Please enter a valid number';
          isValid = false;
        } else {
          if (config.min != null && numVal < config.min) {
            newErrors[key] = `Value must be at least ${config.min}`;
            isValid = false;
          }
          if (config.max != null && numVal > config.max) {
            newErrors[key] = `Value must be at most ${config.max}`;
            isValid = false;
          }
        }
      }

      // Text length validation
      if ((config.fieldType === 'text' || config.fieldType === 'textarea') && value) {
        if (config.minLength != null && value.length < config.minLength) {
          newErrors[key] = `Must be at least ${config.minLength} characters`;
          isValid = false;
        }
        if (config.maxLength != null && value.length > config.maxLength) {
          newErrors[key] = `Must be at most ${config.maxLength} characters`;
          isValid = false;
        }
      }

      // JSON validation
      if (config.fieldType === 'json' && value) {
        try {
          JSON.parse(value);
        } catch {
          newErrors[key] = 'Invalid JSON format';
          isValid = false;
        }
      }
    });

    setErrors(newErrors);
    return isValid;
  };

  const clearError = (key: string) => {
    setErrors((prev) => {
      if (!prev[key]) return prev;
      return { ...prev, [key]: '' };
    });
  };

  return { errors, validate, clearError, setErrors };
}
