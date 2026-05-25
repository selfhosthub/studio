// ui/features/step-config/sections/SetFieldsEditor.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { Plus, Trash2, GripVertical, Copy, ChevronDown } from 'lucide-react';

// Field type config matching n8n style
const FIELD_TYPES = {
  string: { icon: 'AB', label: 'String', color: 'text-success' },
  number: { icon: '#', label: 'Number', color: 'text-info' },
  boolean: { icon: '◐', label: 'Boolean', color: 'text-purple-600 dark:text-purple-400' }, // css-check-ignore: no semantic token
  array: { icon: '[ ]', label: 'Array', color: 'text-critical' },
  object: { icon: '{ }', label: 'Object', color: 'text-warning' },
};

interface FieldDefinition {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'array' | 'object';
  value: any;
  is_expression: boolean;
}

interface SetFieldsConfig {
  mode: 'manual' | 'json';
  fields: FieldDefinition[];
  json_value?: string;
  include_input_fields: boolean;
  input_fields_mode: 'all' | 'selected' | 'none';
  selected_input_fields?: string[];
}

interface SetFieldsEditorProps {
  parameters: Record<string, any>;
  outputFields: Record<string, any>;
  onParametersChange: (parameters: Record<string, any>) => void;
  onOutputFieldsChange: (outputs: Record<string, any>) => void;
}

export default function SetFieldsEditor({
  parameters,
  outputFields,
  onParametersChange,
  onOutputFieldsChange,
}: SetFieldsEditorProps) {
  // Initialize config from parameters
  const [config, setConfig] = useState<SetFieldsConfig>(() => ({
    mode: parameters?.mode || 'manual',
    fields: Array.isArray(parameters?.fields) ? parameters.fields : [],
    json_value: parameters?.json_value || '{}',
    include_input_fields: parameters?.include_input_fields || false,
    input_fields_mode: parameters?.input_fields_mode || 'none',
    selected_input_fields: parameters?.selected_input_fields || [],
  }));

  // Track previous config to avoid redundant updates
  const prevConfigRef = React.useRef<string | null>(null);

  // Sync config changes back to parameters and outputs
  useEffect(() => {
    // Serialize config for comparison
    const configJson = JSON.stringify(config);

    // Skip if config hasn't changed
    if (prevConfigRef.current === configJson) {
      return;
    }
    prevConfigRef.current = configJson;

    // Update parameters
    onParametersChange({
      mode: config.mode,
      fields: config.fields,
      json_value: config.json_value,
      include_input_fields: config.include_input_fields,
      input_fields_mode: config.input_fields_mode,
      selected_input_fields: config.selected_input_fields,
    });

    // Also update step outputs so subsequent steps can see the fields
    // Each field becomes an output that can be mapped to
    // Include the sample_value so downstream steps can preview what will be passed
    const outputs: Record<string, any> = {};
    config.fields.forEach((field) => {
      if (field.name) {
        // For static values, we can show the actual value as sample
        // For expressions, show the expression as a placeholder
        const sampleValue = field.is_expression
          ? `{{${field.value || 'expression'}}}`
          : field.value;

        outputs[field.name] = {
          path: field.name,
          type: field.type,
          description: field.is_expression ? `Expression: ${field.value}` : `Static ${field.type} value`,
          sample_value: sampleValue,
        };
      }
    });
    onOutputFieldsChange(outputs);
  }, [config, onParametersChange, onOutputFieldsChange]);

  // Add a new field
  const addField = () => {
    const newField: FieldDefinition = {
      name: '',
      type: 'string',
      value: '',
      is_expression: false,
    };
    setConfig((prev) => ({
      ...prev,
      fields: [...prev.fields, newField],
    }));
  };

  // Remove a field
  const removeField = (index: number) => {
    setConfig((prev) => ({
      ...prev,
      fields: prev.fields.filter((_, i) => i !== index),
    }));
  };

  // Duplicate a field
  const duplicateField = (index: number) => {
    const field = config.fields[index];
    const newField = { ...field, name: `${field.name}_copy` };
    setConfig((prev) => ({
      ...prev,
      fields: [...prev.fields.slice(0, index + 1), newField, ...prev.fields.slice(index + 1)],
    }));
  };

  // Update a field property
  const updateField = (index: number, updates: Partial<FieldDefinition>) => {
    setConfig((prev) => ({
      ...prev,
      fields: prev.fields.map((field, i) =>
        i === index ? { ...field, ...updates } : field
      ),
    }));
  };

  // Handle type change - try to convert value when changing to array/object
  const handleTypeChange = (index: number, newType: FieldDefinition['type']) => {
    const field = config.fields[index];
    const currentValue = field.value;
    let newValue = currentValue;

    // When changing TO array or object, try to parse string value as JSON
    if ((newType === 'array' || newType === 'object') && typeof currentValue === 'string') {
      const trimmed = currentValue.trim();
      if (trimmed) {
        try {
          const parsed = JSON.parse(trimmed);
          // Validate that parsed type matches target type
          if (newType === 'array' && Array.isArray(parsed)) {
            newValue = parsed;
          } else if (newType === 'object' && typeof parsed === 'object' && !Array.isArray(parsed)) {
            newValue = parsed;
          }
          // If types don't match, keep as string - will show in textarea
        } catch {
          // Not valid JSON, keep as string
        }
      }
    }
    // When changing FROM array/object TO string, stringify the value
    else if (newType === 'string' && (Array.isArray(currentValue) || (typeof currentValue === 'object' && currentValue !== null))) {
      newValue = JSON.stringify(currentValue);
    }

    updateField(index, { type: newType, value: newValue });
  };

  // Render value input based on type and expression mode
  const renderValueInput = (field: FieldDefinition, index: number) => {
    const baseClass = 'w-full bg-transparent border-0 focus:outline-none focus:ring-0 focus-visible:ring-2 focus-visible:ring-[var(--theme-primary)] text-sm text-primary placeholder-muted';

    if (field.is_expression) {
      return (
        <div className="flex items-center gap-2 bg-card rounded px-3 py-2">
          <span className="text-muted font-mono">=</span>
          <input
            type="text"
            value={field.value || ''}
            onChange={(e) => updateField(index, { value: e.target.value })}
            placeholder="{{ $json.field }}"
            className={`${baseClass} font-mono`}
          />
        </div>
      );
    }

    // Fixed value inputs
    switch (field.type) {
      case 'boolean':
        return (
          <div className="bg-card rounded px-3 py-2">
            <select
              value={field.value === true ? 'true' : field.value === false ? 'false' : ''}
              onChange={(e) => updateField(index, { value: e.target.value === 'true' })}
              className={`${baseClass} bg-transparent`}
            >
              <option value="" className="bg-card">Select...</option>
              <option value="true" className="bg-card">true</option>
              <option value="false" className="bg-card">false</option>
            </select>
          </div>
        );

      case 'number':
        return (
          <div className="bg-card rounded px-3 py-2">
            <input
              type="number"
              value={field.value ?? ''}
              onChange={(e) => updateField(index, { value: e.target.value === '' ? '' : Number(e.target.value) })}
              placeholder="0"
              className={baseClass}
            />
          </div>
        );

      case 'array':
      case 'object':
        return (
          <div className="bg-card rounded px-3 py-2">
            <textarea
              value={typeof field.value === 'string' ? field.value : JSON.stringify(field.value, null, 2)}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value);
                  updateField(index, { value: parsed });
                } catch {
                  updateField(index, { value: e.target.value });
                }
              }}
              placeholder={field.type === 'array' ? '["item1", "item2"]' : '{"key": "value"}'}
              rows={3}
              className={`${baseClass}font-mono text-xs resize-none`}
            />
          </div>
        );

      default: // string
        return (
          <div className="bg-card rounded px-3 py-2">
            <input
              type="text"
              value={field.value || ''}
              onChange={(e) => updateField(index, { value: e.target.value })}
              placeholder="value"
              className={baseClass}
            />
          </div>
        );
    }
  };

  return (
    <div className="space-y-4">
      {/* Fields list */}
      <div className="space-y-3">
        {config.fields.map((field, index) => (
          <div
            key={index}
            className="bg-card border border-primary rounded-lg overflow-hidden"
          >
            {/* Field Header Row */}
            <div className="flex items-center border-b border-primary">
              {/* Left side controls */}
              <div className="flex items-center px-2 py-2 border-r border-primary bg-surface">
                <GripVertical size={14} className="text-muted cursor-grab mr-1" />
                <button
                  type="button"
                  onClick={() => removeField(index)}
                  className="p-1 text-muted hover:text-danger transition-colors"
                  title="Delete field"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {/* Expression indicator */}
              {field.is_expression && (
                <div className="px-2 py-2 border-r border-primary bg-surface">
                  <span className="text-critical font-mono text-xs font-bold">fx</span>
                </div>
              )}

              {/* Field name input */}
              <div className="flex-1 min-w-0 px-3 py-2">
                <input
                  type="text"
                  value={field.name}
                  onChange={(e) => updateField(index, { name: e.target.value })}
                  placeholder="name"
                  className="w-full bg-transparent border-0 focus:outline-none focus:ring-0 focus-visible:ring-2 focus-visible:ring-[var(--theme-primary)] text-sm text-primary placeholder-gray-400 dark:placeholder-gray-500"
                />
              </div>

              {/* Duplicate button */}
              <button
                type="button"
                onClick={() => duplicateField(index)}
                className="px-2 py-2 text-muted hover:text-secondary transition-colors"
                title="Duplicate field"
              >
                <Copy size={14} />
              </button>
            </div>

            {/* Type selector row */}
            <div className="flex items-center border-b border-primary px-3 py-2">
              <span className={`font-mono text-xs font-bold mr-2${FIELD_TYPES[field.type].color}`}>
                {FIELD_TYPES[field.type].icon}
              </span>
              <select
                value={field.type}
                onChange={(e) => handleTypeChange(index, e.target.value as FieldDefinition['type'])}
                className="bg-transparent border-0 focus:outline-none focus:ring-0 focus-visible:ring-2 focus-visible:ring-[var(--theme-primary)] text-sm text-secondary cursor-pointer"
              >
                {Object.entries(FIELD_TYPES).map(([type, config]) => (
                  <option key={type} value={type} className="bg-card">
                    {config.label}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="text-muted ml-1" />
            </div>

            {/* Value input row */}
            <div className="px-3 py-2">
              {renderValueInput(field, index)}
            </div>

            {/* Fixed/Expression toggle row */}
            <div className="flex items-center justify-end px-3 py-2 border-t border-primary bg-surface">
              <div className="flex items-center bg-input rounded text-xs overflow-hidden">
                <button
                  type="button"
                  onClick={() => updateField(index, { is_expression: false })}
                  className={`px-3 py-1 transition-colors ${
                    !field.is_expression
                      ? 'bg-surface text-primary'
                      : 'text-secondary hover:text-secondary'
                  }`}
                >
                  Fixed
                </button>
                <button
                  type="button"
                  onClick={() => updateField(index, { is_expression: true })}
                  className={`px-3 py-1 transition-colors ${
                    field.is_expression
                      ? 'bg-surface text-primary'
                      : 'text-secondary hover:text-secondary'
                  }`}
                >
                  Expression
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Add Field button */}
      <button
        type="button"
        onClick={addField}
        className="w-full py-3 border-2 border-dashed border-primary rounded-lg text-secondary hover:border-secondary hover:text-secondary transition-colors flex items-center justify-center gap-2"
      >
        <Plus size={16} />
        <span>Add Field</span>
      </button>

      {/* Options section */}
      <div className="pt-4 border-t border-primary">
        <label className="flex items-center gap-2 text-sm text-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={config.include_input_fields}
            onChange={(e) => setConfig((prev) => ({
              ...prev,
              include_input_fields: e.target.checked,
              input_fields_mode: e.target.checked ? 'all' : 'none',
            }))}
            className="rounded border-primary bg-card text-indigo-500 focus:ring-indigo-500 focus:ring-offset-white dark:focus:ring-offset-gray-900" // css-check-ignore: no semantic token
          />
          Include fields from input
        </label>
      </div>
    </div>
  );
}
