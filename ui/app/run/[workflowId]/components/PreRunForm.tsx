// ui/app/run/[workflowId]/components/PreRunForm.tsx

"use client";

/**
 * PreRunForm - the form a user fills out before starting a workflow instance.
 *
 * Source of truth for fields is the server-side `/workflows/{id}/form-schema`
 * endpoint: every field carries `step_id`, `step_name`, `step_order`, and a
 * fully-derived `config` block with field_type, options, default_value, size,
 * etc. This component groups those fields into collapsible sections by step,
 * renders each widget according to `field_type`, pairs adjacent `size: "half"`
 * fields into 2-col rows (Leonardo width/height), and calls `onSubmit` with
 * the `{step_id}.{param_path}`-keyed value dict when the user clicks Start.
 *
 * No dependency on ExperienceConfig or any `experience_config.input.fields`
 * block. Works for every workflow, with or without an experience config.
 */

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import type { WorkflowFormSchemaResponse, FormFieldResponse } from "@/shared/api";
import {
  FormFieldRenderer,
  collectMissingRequiredFields,
  type RequiredCheckEntry,
} from "@/features/form-field-renderer";
import type { FormFieldConfig, FormFieldType } from "@/entities/workflow";

interface PreRunFormProps {
  workflowName: string;
  workflowDescription?: string;
  formSchema: WorkflowFormSchemaResponse | null;
  submitting: boolean;
  onSubmit: (values: Record<string, unknown>) => void | Promise<void>;
}

interface FieldGroup {
  stepId: string;
  stepName: string;
  stepOrder: number;
  fields: FormFieldResponse[];
}

function fieldKey(field: FormFieldResponse): string {
  return `${field.step_id}.${field.parameter_key}`;
}

function groupFieldsByStep(fields: FormFieldResponse[]): FieldGroup[] {
  const groups = new Map<string, FieldGroup>();
  for (const field of fields) {
    const existing = groups.get(field.step_id);
    if (existing) {
      existing.fields.push(field);
    } else {
      groups.set(field.step_id, {
        stepId: field.step_id,
        stepName: field.step_name || field.step_id,
        stepOrder: field.step_order ?? Number.MAX_SAFE_INTEGER,
        fields: [field],
      });
    }
  }
  return Array.from(groups.values()).sort((a, b) => a.stepOrder - b.stepOrder);
}

function computeInitialDefaults(fields: FormFieldResponse[]): Record<string, unknown> {
  const defaults: Record<string, unknown> = {};
  for (const field of fields) {
    const value = field.config?.default_value;
    if (value !== undefined && value !== null) {
      defaults[fieldKey(field)] = value;
    }
  }
  return defaults;
}

/** Pack consecutive `size: "half"` fields into 2-col rows. */
function packRows(
  fields: FormFieldResponse[],
): Array<FormFieldResponse | [FormFieldResponse, FormFieldResponse]> {
  const rows: Array<FormFieldResponse | [FormFieldResponse, FormFieldResponse]> = [];
  let i = 0;
  while (i < fields.length) {
    const current = fields[i];
    const next = fields[i + 1];
    if (current.config?.size === "half" && next?.config?.size === "half") {
      rows.push([current, next]);
      i += 2;
    } else {
      rows.push(current);
      i += 1;
    }
  }
  return rows;
}

export default function PreRunForm({
  workflowName,
  workflowDescription,
  formSchema,
  submitting,
  onSubmit,
}: PreRunFormProps) {
  const fields = useMemo(() => formSchema?.fields ?? [], [formSchema]);
  const groupedFields = useMemo(() => groupFieldsByStep(fields), [fields]);
  const initialDefaults = useMemo(() => computeInitialDefaults(fields), [fields]);

  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [formInitialized, setFormInitialized] = useState(false);
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const [missingFields, setMissingFields] = useState<string[]>([]);

  // Initialize form values from server-provided defaults once the schema arrives.
  useEffect(() => {
    if (formInitialized) return;
    if (Object.keys(initialDefaults).length === 0) return;
    setFormValues(initialDefaults); // eslint-disable-line react-hooks/set-state-in-effect -- async defaults
    setFormInitialized(true);
  }, [initialDefaults, formInitialized]);

  // Collapse every section except the first on mount; preserve user toggles on later renders.
  useEffect(() => {
    if (groupedFields.length === 0) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async schema
    setCollapsedSections((prev) => {
      const next = { ...prev };
      let changed = false;
      groupedFields.forEach((group, idx) => {
        if (next[group.stepId] === undefined) {
          next[group.stepId] = idx !== 0;
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [groupedFields]);

  // Accordion: clicking a collapsed section opens it and closes every other section.
  const toggleSection = (stepId: string) => {
    setCollapsedSections((prev) => {
      const isCurrentlyCollapsed = prev[stepId];
      const next: Record<string, boolean> = {};
      Object.keys(prev).forEach((k) => {
        next[k] = true;
      });
      if (isCurrentlyCollapsed) {
        next[stepId] = false;
      }
      return next;
    });
  };

  const handleFieldChange = (field: FormFieldResponse, value: unknown) => {
    setFormValues((prev) => ({ ...prev, [fieldKey(field)]: value }));
    if (missingFields.length > 0) setMissingFields([]);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const entries: RequiredCheckEntry[] = fields.map((field) => {
      const key = fieldKey(field);
      const typed = formValues[key];
      const effective = typed !== undefined ? typed : field.config?.default_value;
      return {
        label: field.config?.label || field.parameter_key,
        required: !!field.config?.required,
        value: effective,
      };
    });
    const missing = collectMissingRequiredFields(entries);
    if (missing.length > 0) {
      setMissingFields(missing);
      return;
    }
    setMissingFields([]);
    await onSubmit(formValues);
  };

  // Normalize the snake_case API shape to the camelCase `FormFieldConfig`
  // that `FormFieldRenderer` expects. This is the one boundary conversion
  // for this caller - no other switch on `field_type` should remain.
  const toCanonicalConfig = (
    apiConfig: FormFieldResponse["config"],
    field: FormFieldResponse
  ): FormFieldConfig => ({
    label: apiConfig?.label ?? field.parameter_key,
    placeholder:
      apiConfig?.placeholder ||
      `Enter ${(apiConfig?.label || field.parameter_key).toLowerCase()}...`,
    description: apiConfig?.description,
    required: apiConfig?.required ?? false,
    fieldType: (apiConfig?.field_type as FormFieldType | undefined) ?? "text",
    defaultValue: apiConfig?.default_value,
    options: apiConfig?.options,
    minLength: apiConfig?.min_length,
    maxLength: apiConfig?.max_length,
    min: apiConfig?.min,
    max: apiConfig?.max,
    acceptedFileTypes: apiConfig?.accepted_file_types,
    maxFileSizeMB: apiConfig?.max_file_size_mb,
    size: apiConfig?.size as FormFieldConfig["size"],
    itemType: apiConfig?.item_type,
    keyPlaceholder: apiConfig?.key_placeholder,
    valuePlaceholder: apiConfig?.value_placeholder,
    addLabel: apiConfig?.add_label,
  });

  const renderFieldInput = (field: FormFieldResponse, autoFocus: boolean) => {
    const key = fieldKey(field);
    return (
      <FormFieldRenderer
        config={toCanonicalConfig(field.config, field)}
        value={formValues[key]}
        onChange={(next) => handleFieldChange(field, next)}
        paramKey={key}
        autoFocus={autoFocus}
      />
    );
  };

  const renderFieldWithLabel = (field: FormFieldResponse, autoFocus: boolean) => (
    <div>
      {field.config?.label && (
        <label className="block text-sm font-medium text-secondary mb-2">
          {field.config.label}
          {field.config.required && <span className="text-danger ml-1">*</span>}
        </label>
      )}
      {renderFieldInput(field, autoFocus)}
    </div>
  );

  const firstFieldKey = groupedFields[0]?.fields[0]
    ? fieldKey(groupedFields[0].fields[0])
    : null;

  return (
    <div className="experience-bg">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-blue-500/5 rounded-full blur-3xl" /> {/* css-check-ignore: decorative blur orb */}
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-purple-500/5 rounded-full blur-3xl" /> {/* css-check-ignore: decorative blur orb */}
      </div>

      <div className="w-full max-w-lg relative">
        <div className="experience-card">
          <div className="px-8 pt-8 pb-6 text-center border-b border-secondary">
            <h1 className="text-2xl font-semibold text-primary">{workflowName}</h1>
            {workflowDescription && (
              <p className="mt-2 text-secondary text-sm">{workflowDescription}</p>
            )}
          </div>

          <form onSubmit={handleSubmit} className="px-8 py-6" noValidate>
            {groupedFields.length === 0 ? (
              <p className="text-sm text-muted text-center py-4">
                This workflow has no input fields. Click Start to run it as-is.
              </p>
            ) : (
              <div className="space-y-3">
                {groupedFields.map((group) => {
                  const isCollapsed = collapsedSections[group.stepId] ?? true;
                  const rows = packRows(group.fields);
                  return (
                    <div
                      key={group.stepId}
                      className={`experience-section ${!isCollapsed ? "experience-section-open" : ""}`}
                    >
                      <button
                        type="button"
                        onClick={() => toggleSection(group.stepId)}
                        className="w-full flex items-center justify-between px-4 py-3 hover:bg-input transition-colors"
                        aria-expanded={!isCollapsed}
                      >
                        <span className="flex items-center gap-2">
                          {isCollapsed ? (
                            <ChevronRight className="w-4 h-4 text-secondary" />
                          ) : (
                            <ChevronDown className="w-4 h-4 text-secondary" />
                          )}
                          <span className="text-sm font-medium text-primary">{group.stepName}</span>
                          <span className="text-xs text-muted">
                            {group.fields.length} {group.fields.length === 1 ? "field" : "fields"}
                          </span>
                        </span>
                      </button>
                      {!isCollapsed && (
                        <div className="px-4 py-4 space-y-4 border-t border-secondary">
                          {rows.map((row, rowIdx) => {
                            if (Array.isArray(row)) {
                              return (
                                <div key={rowIdx} className="grid grid-cols-2 gap-3">
                                  {renderFieldWithLabel(
                                    row[0],
                                    firstFieldKey === fieldKey(row[0]),
                                  )}
                                  {renderFieldWithLabel(row[1], false)}
                                </div>
                              );
                            }
                            return (
                              <div key={rowIdx}>
                                {renderFieldWithLabel(
                                  row,
                                  firstFieldKey === fieldKey(row),
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {missingFields.length > 0 && (
              <div className="alert alert-error mt-4" role="alert">
                <p className="text-sm text-danger">
                  Please fill in required field
                  {missingFields.length > 1 ? "s" : ""}: {missingFields.join(", ")}
                </p>
              </div>
            )}
            <button
              type="submit"
              disabled={submitting}
              className="btn-cta mt-6"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Starting...
                </>
              ) : (
                "Start"
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
