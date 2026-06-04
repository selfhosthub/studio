// ui/widgets/flow-editor/WorkflowFormModal.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { X, Play, Loader2 } from 'lucide-react';
import { WorkflowFormSchema, FormField, FormFieldConfig } from '@/entities/workflow';
import { Modal } from '@/shared/ui';

interface WorkflowFormModalProps {
  workflowId: string;
  workflowName: string;
  formSchema: WorkflowFormSchema;
  onClose: () => void;
  onSubmit: (formValues: Record<string, any>) => void;
  isSubmitting: boolean;
}

/**
 * Modal for collecting form inputs when running a workflow.
 * Renders dynamic form fields based on the workflow's form schema.
 */
export default function WorkflowFormModal({
  workflowId,
  workflowName,
  formSchema,
  onClose,
  onSubmit,
  isSubmitting,
}: WorkflowFormModalProps) {
  // Form state: keyed by "{step_id}.{parameter_key}"
  const [formValues, setFormValues] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Initialize form values with defaults
  useEffect(() => {
    const initialValues: Record<string, any> = {};
    formSchema.fields.forEach((field) => {
      const key = `${field.step_id}.${field.parameter_key}`;
      if (field.config.defaultValue !== undefined) {
        initialValues[key] = field.config.defaultValue;
      } else if (field.config.fieldType === 'checkbox') {
        initialValues[key] = false;
      } else {
        initialValues[key] = '';
      }
    });
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFormValues(initialValues);
  }, [formSchema]);

  // Update a single field value
  const updateValue = (stepId: string, paramKey: string, value: any) => {
    const key = `${stepId}.${paramKey}`;
    setFormValues((prev) => ({ ...prev, [key]: value }));
    // Clear error when user types
    if (errors[key]) {
      setErrors((prev) => ({ ...prev, [key]: '' }));
    }
  };

  // Validate form before submission
  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};
    let isValid = true;

    formSchema.fields.forEach((field) => {
      const key = `${field.step_id}.${field.parameter_key}`;
      const value = formValues[key];

      if (field.config.required) {
        if (value === undefined || value === null || value === '') {
          newErrors[key] = `${field.config.label} is required`;
          isValid = false;
        }
      }

      // Number validation (check for both null and undefined)
      if (field.config.fieldType === 'number' && value !== '' && value != null) {
        const numVal = Number(value);
        if (isNaN(numVal)) {
          newErrors[key] = 'Please enter a valid number';
          isValid = false;
        } else {
          if (field.config.min != null && numVal < field.config.min) {
            newErrors[key] = `Value must be at least ${field.config.min}`;
            isValid = false;
          }
          if (field.config.max != null && numVal > field.config.max) {
            newErrors[key] = `Value must be at most ${field.config.max}`;
            isValid = false;
          }
        }
      }

      // Text length validation (check for both null and undefined)
      if ((field.config.fieldType === 'text' || field.config.fieldType === 'textarea') && value) {
        if (field.config.minLength != null && value.length < field.config.minLength) {
          newErrors[key] = `Must be at least ${field.config.minLength} characters`;
          isValid = false;
        }
        if (field.config.maxLength != null && value.length > field.config.maxLength) {
          newErrors[key] = `Must be at most ${field.config.maxLength} characters`;
          isValid = false;
        }
      }
    });

    setErrors(newErrors);
    return isValid;
  };

  // Handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validateForm()) {
      onSubmit(formValues);
    }
  };

  // Render a single form field
  const renderField = (field: FormField) => {
    const key = `${field.step_id}.${field.parameter_key}`;
    const value = formValues[key] ?? '';
    const error = errors[key];
    const config = field.config;

    const inputBaseClass = 'form-input';
    const inputErrorClass = error
      ? ' border-danger'
      : '';

    switch (config.fieldType) {
      case 'textarea':
        return (
          <textarea
            value={value}
            onChange={(e) => updateValue(field.step_id, field.parameter_key, e.target.value)}
            placeholder={config.placeholder}
            rows={4}
            className={`${inputBaseClass}${inputErrorClass}`}
          />
        );

      case 'number':
        return (
          <input
            type="number"
            value={value}
            onChange={(e) => updateValue(field.step_id, field.parameter_key, e.target.value)}
            placeholder={config.placeholder}
            min={config.min}
            max={config.max}
            className={`${inputBaseClass}${inputErrorClass}`}
          />
        );

      case 'select':
        return (
          <select
            value={value}
            onChange={(e) => updateValue(field.step_id, field.parameter_key, e.target.value)}
            className={`${inputBaseClass}${inputErrorClass}`}
          >
            <option value="">Select an option...</option>
            {config.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        );

      case 'checkbox':
        return (
          <div className="flex items-center">
            <input
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => updateValue(field.step_id, field.parameter_key, e.target.checked)}
              className="h-4 w-4 text-info focus:ring-blue-500 border-primary rounded"
            />
            {config.description && (
              <span className="ml-2 text-sm text-secondary">
                {config.description}
              </span>
            )}
          </div>
        );

      case 'date':
        return (
          <input
            type="date"
            value={value}
            onChange={(e) => updateValue(field.step_id, field.parameter_key, e.target.value)}
            className={`${inputBaseClass}${inputErrorClass}`}
          />
        );

      case 'datetime':
        return (
          <input
            type="datetime-local"
            value={value}
            onChange={(e) => updateValue(field.step_id, field.parameter_key, e.target.value)}
            className={`${inputBaseClass}${inputErrorClass}`}
          />
        );

      case 'text':
      default:
        return (
          <input
            type="text"
            value={value}
            onChange={(e) => updateValue(field.step_id, field.parameter_key, e.target.value)}
            placeholder={config.placeholder}
            maxLength={config.maxLength}
            className={`${inputBaseClass}${inputErrorClass}`}
          />
        );
    }
  };

  // Group fields by step for better organization
  const fieldsByStep = formSchema.fields.reduce((acc, field) => {
    const stepName = field.step_name;
    if (!acc[stepName]) {
      acc[stepName] = [];
    }
    acc[stepName].push(field);
    return acc;
  }, {} as Record<string, FormField[]>);

  const stepNames = Object.keys(fieldsByStep);
  const showStepHeaders = stepNames.length > 1;

  return (
    <Modal isOpen={true} onClose={onClose} size="md">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-primary px-6 py-4">
            <div>
              <h3 className="text-lg font-semibold text-primary">
                Run: {workflowName}
              </h3>
              <p className="mt-1 text-sm text-secondary">
                Fill in the required information to run this workflow
              </p>
            </div>
            <button
              onClick={onClose}
              disabled={isSubmitting}
              aria-label="Close"
              className="text-muted hover:text-secondary disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit}>
            <div className="px-6 py-4 max-h-[60vh] overflow-y-auto">
              {formSchema.fields.length === 0 ? (
                <p className="text-center text-secondary py-4">
                  This workflow has no form inputs. Click &quot;Run Workflow&quot; to start.
                </p>
              ) : (
                <div className="space-y-6">
                  {stepNames.map((stepName) => (
                    <div key={stepName}>
                      {showStepHeaders && (
                        <h4 className="text-sm font-medium text-secondary mb-3 pb-2 border-b border-secondary">
                          {stepName}
                        </h4>
                      )}
                      <div className="space-y-4">
                        {fieldsByStep[stepName].map((field) => {
                          const key = `${field.step_id}.${field.parameter_key}`;
                          const error = errors[key];
                          const config = field.config;

                          return (
                            <div key={key}>
                              {config.fieldType !== 'checkbox' && (
                                <label className="block text-sm font-medium text-secondary mb-1">
                                  {config.label}
                                  {config.required && (
                                    <span className="text-danger ml-1">*</span>
                                  )}
                                </label>
                              )}
                              {renderField(field)}
                              {config.fieldType !== 'checkbox' && config.description && (
                                <p className="mt-1 text-xs text-secondary">
                                  {config.description}
                                </p>
                              )}
                              {error && (
                                <p className="mt-1 text-xs text-danger">{error}</p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 border-t border-primary px-6 py-4">
              <button
                type="button"
                onClick={onClose}
                disabled={isSubmitting}
                className="px-4 py-2 text-sm font-medium text-secondary bg-card border border-primary rounded-md hover:bg-surface disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="btn-primary inline-flex items-center text-sm"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    Run Workflow
                  </>
                )}
              </button>
            </div>
          </form>
    </Modal>
  );
}
