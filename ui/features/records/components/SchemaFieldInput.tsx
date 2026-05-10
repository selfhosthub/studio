// ui/features/records/components/SchemaFieldInput.tsx

'use client';

import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';

/**
 * Generic field types supported by the RecordEditor.
 * Provider-specific types should map to these via fieldTypeMapping in adapter-config.json.
 */
export type GenericFieldType =
  | 'text'       // Single line text
  | 'textarea'   // Multi-line text
  | 'number'     // Numeric input
  | 'select'     // Single select dropdown
  | 'multiselect'// Multi-select
  | 'checkbox'   // Boolean checkbox
  | 'date'       // Date picker
  | 'datetime'   // DateTime picker
  | 'array'      // JSON array (attachments, etc.)
  | 'reference'; // Linked records/foreign keys

/**
 * Standardized field schema returned by the backend.
 * All providers should normalize their schema to this format.
 */
export interface FieldSchema {
  name: string;
  type: GenericFieldType;
  description?: string | null;
  required?: boolean;
  options?: {
    choices?: Array<{ id: string; name: string; color?: string }>;
    precision?: number;
    symbol?: string;
    format?: string;
    [key: string]: any;
  };
  is_computed?: boolean;
}

export interface FieldValue {
  value: any;
  is_expression: boolean;
}

interface SchemaFieldInputProps {
  field: FieldSchema;
  fieldValue: FieldValue;
  onChange: (value: FieldValue) => void;
}

/**
 * Generic field input component that renders appropriate UI based on field type.
 * Works with any provider that returns a standardized FieldSchema.
 */
export default function SchemaFieldInput({
  field,
  fieldValue,
  onChange,
}: SchemaFieldInputProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const baseInputClass = 'w-full bg-transparent border-0 focus:outline-none focus:ring-0 focus-visible:ring-2 focus-visible:ring-[var(--theme-primary)] text-sm text-primary placeholder-muted';

  // Update value while preserving expression mode
  const updateValue = (newValue: any) => {
    onChange({ ...fieldValue, value: newValue });
  };

  // Toggle between fixed and expression mode
  const toggleMode = (isExpression: boolean) => {
    onChange({ ...fieldValue, is_expression: isExpression, value: isExpression ? '' : fieldValue.value });
  };

  // Drag-drop handlers for mapping fields from previous steps
  // stopPropagation prevents parent MappableParameterField from blocking drops on complex arrays
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes('application/x-field-mapping')) {
      e.dataTransfer.dropEffect = 'copy';
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.stopPropagation();
    // Only clear if we're actually leaving the component (not entering a child)
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const rawData = e.dataTransfer.getData('application/x-field-mapping');
    if (!rawData) return;

    try {
      const { stepId, fieldName } = JSON.parse(rawData);
      // Switch to expression mode and set the template
      onChange({
        value: `{{ steps.${stepId}.${fieldName} }}`,
        is_expression: true,
      });
    } catch (err) {
      console.error('Failed to parse drag data:', err);
    }
  };

  // Render expression input
  if (fieldValue.is_expression) {
    return (
      <div
        className={`space-y-2 relative rounded-lg p-2 -m-2 transition-all ${
          isDragOver ? 'ring-2 ring-blue-500 bg-info-subtle' : ''
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Drop indicator overlay */}
        {isDragOver && (
          <div className="absolute inset-0 flex items-center justify-center bg-info-subtle/80 rounded-lg pointer-events-none z-10">
            <span className="text-sm font-medium text-info">
              Drop to map field
            </span>
          </div>
        )}

        {/* Field label */}
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-secondary">
            {field.name}
          </label>
          {field.required && <span className="text-danger text-xs">*</span>}
        </div>

        <div className="flex items-center gap-2 bg-card rounded px-3 py-2">
          <span className="text-orange-500 dark:text-orange-400 font-mono text-sm">=</span> {/* css-check-ignore: no semantic token */}
          <input
            type="text"
            value={fieldValue.value || ''}
            onChange={(e) => updateValue(e.target.value)}
            placeholder="{{ steps.step_name.field }}"
            className={`${baseInputClass} font-mono`}
          />
        </div>
        <div className="flex justify-end">
          <ModeToggle isExpression={true} onToggle={toggleMode} />
        </div>
      </div>
    );
  }

  // Render type-specific input for fixed values
  const renderInput = () => {
    switch (field.type) {
      case 'checkbox':
        return (
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={fieldValue.value === true}
              onChange={(e) => updateValue(e.target.checked)}
              className="rounded border-primary bg-card text-info focus:ring-blue-500"
            />
            <span className="text-sm text-secondary">
              {fieldValue.value ? 'Checked' : 'Unchecked'}
            </span>
          </label>
        );

      case 'select':
        const choices = field.options?.choices || [];
        return (
          <div className="relative">
            <select
              value={fieldValue.value || ''}
              onChange={(e) => updateValue(e.target.value)}
              className="w-full px-3 py-2 border border-primary rounded-md shadow-sm bg-card text-sm text-primary focus:ring-2 focus:ring-blue-500 focus:border-info appearance-none"
            >
              <option value="">Select...</option>
              {choices.map((choice) => (
                <option key={choice.id} value={choice.name}>
                  {choice.name}
                </option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
          </div>
        );

      case 'multiselect':
        const multiChoices = field.options?.choices || [];
        const selectedValues = Array.isArray(fieldValue.value) ? fieldValue.value : [];
        return (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1 min-h-[32px] p-2 border border-primary rounded-md bg-card">
              {selectedValues.map((val: string, idx: number) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1 px-2 py-0.5 bg-info-subtle text-info text-sm rounded"
                >
                  {val}
                  <button
                    type="button"
                    onClick={() => updateValue(selectedValues.filter((_: string, i: number) => i !== idx))}
                    className="hover:text-info"
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
            <select
              value=""
              onChange={(e) => {
                if (e.target.value && !selectedValues.includes(e.target.value)) {
                  updateValue([...selectedValues, e.target.value]);
                }
              }}
              className="w-full px-3 py-2 border border-primary rounded-md shadow-sm bg-card text-sm text-primary focus:ring-2 focus:ring-blue-500 focus:border-info"
            >
              <option value="">Add option...</option>
              {multiChoices
                .filter((choice) => !selectedValues.includes(choice.name))
                .map((choice) => (
                  <option key={choice.id} value={choice.name}>
                    {choice.name}
                  </option>
                ))}
            </select>
          </div>
        );

      case 'number':
        return (
          <div className="flex items-center gap-2">
            {field.options?.symbol && (
              <span className="text-muted">{field.options.symbol}</span>
            )}
            <input
              type="number"
              value={fieldValue.value ?? ''}
              onChange={(e) => updateValue(e.target.value === '' ? null : Number(e.target.value))}
              placeholder="0"
              step={field.options?.precision ? Math.pow(10, -field.options.precision) : 1}
              className={`${baseInputClass} px-3 py-2 border border-primary rounded-md shadow-sm bg-card`}
            />
          </div>
        );

      case 'date':
        return (
          <input
            type="date"
            value={fieldValue.value || ''}
            onChange={(e) => updateValue(e.target.value)}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm bg-card text-sm text-primary focus:ring-2 focus:ring-blue-500 focus:border-info"
          />
        );

      case 'datetime':
        return (
          <input
            type="datetime-local"
            value={fieldValue.value || ''}
            onChange={(e) => updateValue(e.target.value)}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm bg-card text-sm text-primary focus:ring-2 focus:ring-blue-500 focus:border-info"
          />
        );

      case 'textarea':
        return (
          <textarea
            value={fieldValue.value || ''}
            onChange={(e) => updateValue(e.target.value)}
            placeholder={`Enter ${field.name}...`}
            rows={3}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm bg-card text-sm text-primary focus:ring-2 focus:ring-blue-500 focus:border-info resize-y"
          />
        );

      case 'array':
        // JSON array input for attachments, etc.
        return (
          <div className="space-y-2">
            <textarea
              value={typeof fieldValue.value === 'string' ? fieldValue.value : JSON.stringify(fieldValue.value || [], null, 2)}
              onChange={(e) => {
                try {
                  updateValue(JSON.parse(e.target.value));
                } catch {
                  updateValue(e.target.value);
                }
              }}
              placeholder='[{"url": "https://..."}]'
              rows={3}
              className="w-full px-3 py-2 border border-primary rounded-md shadow-sm bg-card text-sm text-primary font-mono focus:ring-2 focus:ring-blue-500 focus:border-info resize-y"
            />
            <p className="text-muted text-xs">
              Enter JSON array
            </p>
          </div>
        );

      case 'reference':
        // Linked records - comma-separated IDs
        const linkedIds = Array.isArray(fieldValue.value)
          ? fieldValue.value
          : (fieldValue.value || '').split(',').filter(Boolean).map((s: string) => s.trim());
        return (
          <div className="space-y-2">
            <input
              type="text"
              value={linkedIds.join(', ')}
              onChange={(e) => updateValue(e.target.value.split(',').filter(Boolean).map(s => s.trim()))}
              placeholder="id1, id2, ..."
              className="w-full px-3 py-2 border border-primary rounded-md shadow-sm bg-card text-sm text-primary focus:ring-2 focus:ring-blue-500 focus:border-info"
            />
            <p className="text-muted text-xs">
              Enter record IDs separated by commas
            </p>
          </div>
        );

      // Default: text input
      case 'text':
      default:
        return (
          <input
            type="text"
            value={fieldValue.value || ''}
            onChange={(e) => updateValue(e.target.value)}
            placeholder={`Enter ${field.name}...`}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm bg-card text-sm text-primary focus:ring-2 focus:ring-blue-500 focus:border-info"
          />
        );
    }
  };

  return (
    <div
      className={`space-y-2 relative rounded-lg p-2 -m-2 transition-all ${
        isDragOver ? 'ring-2 ring-blue-500 bg-info-subtle' : ''
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drop indicator overlay */}
      {isDragOver && (
        <div className="absolute inset-0 flex items-center justify-center bg-info-subtle/80 rounded-lg pointer-events-none z-10">
          <span className="text-sm font-medium text-info">
            Drop to map field
          </span>
        </div>
      )}

      {/* Field label */}
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium text-secondary">
          {field.name}
        </label>
        {field.required && <span className="text-danger text-xs">*</span>}
        {field.is_computed && (
          <span className="text-xs text-muted dark:text-secondary italic">(computed)</span>
        )}
      </div>

      {/* Input or computed message */}
      {field.is_computed ? (
        <p className="text-sm text-muted dark:text-secondary italic px-3 py-2 bg-surface rounded-md">
          This field is computed and cannot be set directly
        </p>
      ) : (
        <>
          {renderInput()}
          <div className="flex justify-end">
            <ModeToggle isExpression={false} onToggle={toggleMode} />
          </div>
        </>
      )}
    </div>
  );
}

// Toggle between Fixed and Expression mode
function ModeToggle({
  isExpression,
  onToggle,
}: {
  isExpression: boolean;
  onToggle: (isExpression: boolean) => void;
}) {
  return (
    <div className="flex items-center bg-input rounded text-xs overflow-hidden">
      <button
        type="button"
        onClick={() => onToggle(false)}
        className={`px-2 py-1 transition-colors ${
          !isExpression
            ? 'bg-surface text-primary'
            : 'text-secondary hover:text-secondary'
        }`}
      >
        Fixed
      </button>
      <button
        type="button"
        onClick={() => onToggle(true)}
        className={`px-2 py-1 transition-colors ${
          isExpression
            ? 'bg-surface text-primary'
            : 'text-secondary hover:text-secondary'
        }`}
      >
        Expression
      </button>
    </div>
  );
}
