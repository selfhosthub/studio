// ui/widgets/flow-editor/FormInputPanel/index.tsx

'use client';

import React from 'react';
import { Play, Loader2 } from 'lucide-react';
import { WorkflowFormSchema, FormField } from '@/entities/workflow';
import { useFormInputState, normalizeFormFieldConfig, getFormFieldSizeClass } from './hooks/useFormInputState';
import { useFormValidation } from './hooks/useFormValidation';
import { FormFieldPreview } from './components/FormFieldPreview';

interface FormInputPanelProps {
  formSchema: WorkflowFormSchema;
  onSubmit: (formValues: Record<string, any>) => void;
  isSubmitting: boolean;
  initialValues?: Record<string, any>;
}

/**
 * Inline panel for collecting form inputs before running a workflow instance.
 * Displayed on the instance detail page when the workflow has form fields.
 */
export default function FormInputPanel({
  formSchema,
  onSubmit,
  isSubmitting,
  initialValues,
}: FormInputPanelProps) {
  const { errors, validate, clearError } = useFormValidation(formSchema);
  const { formValues, updateValue } = useFormInputState(formSchema, initialValues, clearError);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate(formValues)) {
      onSubmit(formValues);
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
    <div className="bg-card rounded-lg border border-primary shadow-sm">
      {/* Header */}
      <div className="border-b border-primary px-6 py-4">
        <h3 className="text-lg font-semibold text-primary">
          Workflow Inputs
        </h3>
        <p className="mt-1 text-sm text-secondary">
          Fill in the required information to run this workflow
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit}>
        <div className="px-6 py-4">
          {formSchema.fields.length === 0 ? (
            <p className="text-center text-secondary py-4">
              This workflow has no form inputs. Click &quot;Run Workflow&quot; to start.
            </p>
          ) : (
            <div className="space-y-6">
              {stepNames.map((stepName) => (
                <div key={stepName}>
                  {showStepHeaders && (
                    <h4 className="text-sm font-medium text-secondary mb-3 pb-2 border-b border-primary">
                      {stepName}
                    </h4>
                  )}
                  {/* 2-column responsive grid: 1 col on mobile, 2 cols on lg+ screens */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {fieldsByStep[stepName].map((field) => {
                      const key = `${field.step_id}.${field.parameter_key}`;
                      const error = errors[key];
                      const config = normalizeFormFieldConfig(field.config);
                      const sizeClass = getFormFieldSizeClass(config);

                      return (
                        <div key={key} className={sizeClass}>
                          {config.fieldType !== 'checkbox' && (
                            <label className="block text-sm font-medium text-secondary mb-1">
                              {config.label}
                              {config.required && (
                                <span className="text-danger ml-1">*</span>
                              )}
                            </label>
                          )}
                          <FormFieldPreview
                            field={field}
                            config={config}
                            value={formValues[key] ?? ''}
                            error={error}
                            onChange={updateValue}
                          />
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

        {/* Footer with Run button */}
        <div className="flex items-center justify-end border-t border-primary px-6 py-4">
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
    </div>
  );
}
