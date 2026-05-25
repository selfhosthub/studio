// ui/widgets/instance-view/InstanceSimpleView/components/InputsPanel.tsx

"use client";

import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import { FormField } from "@/entities/workflow";
import {
  FormFieldRenderer,
  collectMissingRequiredFields,
  type RequiredCheckEntry,
} from "@/features/form-field-renderer";
import { JsonTreeView } from "./JsonTreeView";
import { normalizeConfig, extractDisplayValues } from "../utils";
import { InstanceSimpleViewProps } from "../types";

interface InputsPanelProps {
  instance: InstanceSimpleViewProps["instance"];
  formSchema: InstanceSimpleViewProps["formSchema"];
  formValues: Record<string, unknown>;
  setFormValues: React.Dispatch<React.SetStateAction<Record<string, unknown>>>;
  onFormSubmit: InstanceSimpleViewProps["onFormSubmit"];
  isSubmittingForm: boolean;
}

export function InputsPanel({
  instance,
  formSchema,
  formValues,
  setFormValues,
  onFormSubmit,
  isSubmittingForm,
}: InputsPanelProps) {
  const [missingFields, setMissingFields] = useState<string[]>([]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const fields = formSchema?.fields || [];
    const finalValues: Record<string, unknown> = {};
    const entries: RequiredCheckEntry[] = [];

    for (const field of fields) {
      const cfg = normalizeConfig(field.config);
      const key = `${field.step_id}.${field.parameter_key}`;
      const saved =
        instance.input_data?.form_values?.[key] ??
        instance.input_data?.[key] ??
        instance.input_data?.[field.parameter_key] ??
        cfg.defaultValue ??
        "";
      if (saved !== "") finalValues[key] = saved;

      const typed = formValues[key];
      const effective = typed !== undefined ? typed : saved;
      entries.push({
        label: cfg.label || field.parameter_key,
        required: !!cfg.required,
        value: effective,
      });
    }

    const missing = collectMissingRequiredFields(entries);
    if (missing.length > 0) {
      setMissingFields(missing);
      return;
    }
    setMissingFields([]);
    onFormSubmit({ ...finalValues, ...formValues });
  };

  const handleChange = (formValueKey: string, newValue: unknown) => {
    setFormValues((prev) => ({ ...prev, [formValueKey]: newValue }));
    if (missingFields.length > 0) setMissingFields([]);
  };

  return (
    <div className="p-4 space-y-4">
      <div className="bg-card rounded-lg border border-primary p-4">
        <h3 className="text-lg font-medium text-primary mb-4">Input Parameters</h3>

        {formSchema?.fields && formSchema.fields.length > 0 ? (
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {formSchema.fields.map((field: FormField) => {
              const config = normalizeConfig(field.config);
              const formValueKey = `${field.step_id}.${field.parameter_key}`;
              const savedValue =
                instance.input_data?.form_values?.[formValueKey] ??
                instance.input_data?.[formValueKey] ??
                instance.input_data?.[field.parameter_key] ??
                config.defaultValue ??
                "";
              const value =
                formValues[formValueKey] !== undefined ? formValues[formValueKey] : savedValue;

              return (
                <div key={formValueKey}>
                  <label className="block text-sm font-medium text-secondary mb-1">
                    {config.label}
                    {config.required && <span className="text-danger ml-1">*</span>}
                  </label>
                  {config.description && (
                    <p className="text-xs text-secondary mb-1">{config.description}</p>
                  )}
                  <FormFieldRenderer
                    config={config}
                    value={value}
                    onChange={(next) => handleChange(formValueKey, next)}
                    paramKey={formValueKey}
                  />
                </div>
              );
            })}

            {missingFields.length > 0 && (
              <div className="alert alert-error" role="alert">
                <p className="text-sm text-danger">
                  Please fill in required field
                  {missingFields.length > 1 ? "s" : ""}: {missingFields.join(", ")}
                </p>
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmittingForm}
              className="btn-primary w-full mt-4 py-2.5 flex items-center justify-center gap-2"
            >
              {isSubmittingForm ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Submitting...
                </>
              ) : (
                "Submit & Start"
              )}
            </button>
          </form>
        ) : instance.input_data && Object.keys(instance.input_data).length > 0 ? (
          <div className="space-y-3">
            {extractDisplayValues(instance.input_data).map(({ key, label, value }) => (
              <div key={key}>
                <label className="block text-sm font-medium text-secondary mb-1">{label}</label>
                <div className="px-3 py-2 bg-surface rounded-md border border-primary text-sm text-primary">
                  {typeof value === "object"
                    ? JSON.stringify(value, null, 2)
                    : String(value ?? "\u2014")}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-secondary italic">No inputs provided</p>
        )}
      </div>

      <JsonTreeView
        id="inputs-raw"
        title="Raw Input Data"
        data={instance.input_data}
        fallbackText="No input data"
      />
    </div>
  );
}
