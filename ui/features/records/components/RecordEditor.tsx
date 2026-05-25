// ui/features/records/components/RecordEditor.tsx

'use client';

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Plus, Trash2, Code, Layout, ChevronDown, ChevronRight, AlertCircle, Loader2 } from 'lucide-react';
import SchemaFieldInput, { FieldSchema, FieldValue } from './SchemaFieldInput';
import { apiRequest } from '@/shared/api';
import { Step } from '@/entities/workflow';
import { isExpression, resolveValue } from '@/shared/lib/expression-utils';

/**
 * Schema response from the backend.
 * All providers should return this standardized format.
 */
interface TableSchema {
  table_name: string;
  fields: FieldSchema[];
}

interface RecordData {
  id?: string; // For update operations
  fields: Record<string, FieldValue>;
}

/**
 * Configuration for the record editor widget.
 * Defined in adapter-config.json ui.schemaConfig.
 */
export interface RecordEditorConfig {
  /** Service to call for fetching schema (e.g., 'get_table_schema') */
  schemaService?: string;
  /** Which parameter contains the table identifier (e.g., 'table_id') */
  tableParam?: string;
  /** Fields that the schema service depends on */
  dependsOn?: string[];
  /** Parameter names to pass to schema service (maps from dependsOn fields) */
  schemaParams?: Record<string, string>;
  /** Whether this is an update operation (requires record ID) */
  isUpdate?: boolean;
}

interface RecordEditorProps {
  value: any[];
  onChange: (value: any[]) => void;
  providerId?: string;
  credentialId?: string;
  /** Field values from other parameters (for schema service dependencies) */
  fieldValues?: Record<string, any>;
  /** Widget configuration from adapter-config.json */
  config?: RecordEditorConfig;
  previousSteps?: Step[]; // For resolving expressions from previous steps
}

/**
 * Generic record editor component for creating/updating records in any data source.
 * Works with any provider that implements the table-schema endpoint.
 *
 * Configuration is done via adapter-config.json:
 * ```json
 * "ui": {
 *   "widget": "record-editor",
 *   "schemaConfig": {
 *     "schemaService": "get_table_schema",
 *     "dependsOn": ["base_id", "table_id"],
 *     "schemaParams": { "base_id": "base_id", "table_id": "table_id" },
 *     "isUpdate": false
 *   }
 * }
 * ```
 */
export default function RecordEditor({
  value,
  onChange,
  providerId,
  credentialId,
  fieldValues = {},
  config = {},
  previousSteps = [],
}: RecordEditorProps) {
  const [mode, setMode] = useState<'form' | 'json'>('form');
  const [schema, setSchema] = useState<TableSchema | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedRecords, setExpandedRecords] = useState<Set<number>>(new Set([0]));
  const [jsonValue, setJsonValue] = useState('');
  const lastFetchRef = useRef<string>('');

  const { schemaService, tableParam = 'table_id', dependsOn = [], schemaParams = {}, isUpdate = false } = config;

  // Convert external value to internal record structure
  const [records, setRecords] = useState<RecordData[]>(() => {
    if (!value || !Array.isArray(value) || value.length === 0) {
      return [{ fields: {} }];
    }
    const hasRealData = value.some(rec =>
      rec.fields && Object.values(rec.fields).some(v => v !== '' && v !== null && v !== undefined)
    );
    if (!hasRealData) {
      return [{ fields: {} }];
    }
    return value.map(rec => ({
      id: rec.id,
      fields: Object.fromEntries(
        Object.entries(rec.fields || {}).map(([key, val]) => [
          key,
          { value: val, is_expression: typeof val === 'string' && val.startsWith('{{') }
        ])
      ),
    }));
  });

  // Sync internal records back to external value
  useEffect(() => {
    if (mode === 'form') {
      const externalValue = records.map(rec => {
        const fields: Record<string, any> = {};
        for (const [key, fieldVal] of Object.entries(rec.fields)) {
          if (fieldVal.value !== undefined && fieldVal.value !== null && fieldVal.value !== '') {
            fields[key] = fieldVal.is_expression ? fieldVal.value : fieldVal.value;
          }
        }
        const result: any = { fields };
        if (rec.id) {
          result.id = rec.id;
        }
        return result;
      });
      if (JSON.stringify(externalValue) !== JSON.stringify(value)) {
        onChange(externalValue);
      }
    }
  }, [records, mode]); // eslint-disable-line react-hooks/exhaustive-deps -- value and onChange excluded; effect syncs internal records to parent via onChange, including them would cause infinite update loops

  // Create expression context for resolving values from previous steps
  const expressionContext = useMemo(() => ({ previousSteps }), [previousSteps]);

  // Resolve dependency field values (they may be expressions)
  const resolvedFieldValues = useMemo(() => {
    const resolved: Record<string, any> = {};
    for (const [key, val] of Object.entries(fieldValues)) {
      resolved[key] = resolveValue(val, expressionContext);
    }
    return resolved;
  }, [fieldValues, expressionContext]);

  // Check if all dependencies are resolved (not expressions)
  const dependenciesResolved = useMemo(() => {
    for (const dep of dependsOn) {
      const val = resolvedFieldValues[dep];
      if (!val || isExpression(val)) {
        return false;
      }
    }
    return true;
  }, [dependsOn, resolvedFieldValues]);

  // Fetch table schema when dependencies change
  const fetchSchema = useCallback(async () => {
    if (!providerId || !credentialId || !schemaService) {
      setSchema(null);
      return;
    }

    // Check if we have all required dependencies
    if (dependsOn.length > 0 && !dependenciesResolved) {
      setSchema(null);
      return;
    }

    // Build request parameters from resolved field values
    const parameters: Record<string, any> = {};
    for (const [paramName, fieldName] of Object.entries(schemaParams)) {
      const val = resolvedFieldValues[fieldName];
      if (val) {
        parameters[paramName] = val;
      }
    }

    const fetchKey = `${providerId}:${credentialId}:${schemaService}:${JSON.stringify(parameters)}`;
    if (fetchKey === lastFetchRef.current) {
      return;
    }
    lastFetchRef.current = fetchKey;

    setIsLoading(true);
    setError(null);

    try {
      // Build query params for the generic table-schema endpoint
      const queryParams = new URLSearchParams({
        credential_id: credentialId,
        schema_service: schemaService,
        table_param: tableParam,
      });

      const data = await apiRequest<TableSchema>(
        `/providers/${providerId}/table-schema?${queryParams.toString()}`,
        {
          method: 'POST',
          body: JSON.stringify({ parameters }),
        }
      );
      setSchema(data);

      // Reset record fields to match new schema
      setRecords(prev => prev.map(rec => {
        const updatedFields: Record<string, FieldValue> = {};
        for (const field of data.fields) {
          if (!field.is_computed) {
            const existingValue = rec.fields[field.name];
            updatedFields[field.name] = existingValue || { value: '', is_expression: false };
          }
        }
        return { ...rec, id: rec.id, fields: updatedFields };
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch schema');
      setSchema(null);
    } finally {
      setIsLoading(false);
    }
  }, [providerId, credentialId, schemaService, tableParam, dependsOn, dependenciesResolved, schemaParams, resolvedFieldValues]);

  useEffect(() => {
    fetchSchema();
  }, [fetchSchema]);

  // Update JSON value when switching to JSON mode
  useEffect(() => {
    if (mode === 'json') {
      const recordsWithData = records.map(rec => {
        const fields: Record<string, any> = {};
        for (const [key, fieldVal] of Object.entries(rec.fields)) {
          if (fieldVal.value !== undefined && fieldVal.value !== null && fieldVal.value !== '') {
            fields[key] = fieldVal.value;
          }
        }
        const result: any = { fields };
        if (rec.id) {
          result.id = rec.id;
        }
        return result;
      });
      const hasData = recordsWithData.some(rec => Object.keys(rec.fields).length > 0 || rec.id);
      const formatted = hasData
        ? JSON.stringify(recordsWithData, null, 2)
        : JSON.stringify([{ fields: {} }], null, 2);
      setJsonValue(formatted);
    }
  }, [mode, records]);

  // Handle JSON changes
  const handleJsonChange = (newJson: string) => {
    setJsonValue(newJson);
    try {
      const parsed = JSON.parse(newJson);
      if (Array.isArray(parsed)) {
        onChange(parsed);
      }
    } catch {
      // Invalid JSON, don't update
    }
  };

  // Add a new record
  const addRecord = () => {
    const newFields: Record<string, FieldValue> = {};
    if (schema) {
      for (const field of schema.fields) {
        if (!field.is_computed) {
          newFields[field.name] = { value: '', is_expression: false };
        }
      }
    }
    const newIndex = records.length;
    setRecords([...records, { fields: newFields }]);
    setExpandedRecords(prev => new Set([...prev, newIndex]));
  };

  // Remove a record
  const removeRecord = (index: number) => {
    if (records.length <= 1) return;
    setRecords(records.filter((_, i) => i !== index));
    setExpandedRecords(prev => {
      const newSet = new Set(prev);
      newSet.delete(index);
      return new Set([...newSet].map(i => i > index ? i - 1 : i));
    });
  };

  // Update a field in a record
  const updateField = (recordIndex: number, fieldName: string, fieldValue: FieldValue) => {
    setRecords(prev => prev.map((rec, i) =>
      i === recordIndex
        ? { ...rec, fields: { ...rec.fields, [fieldName]: fieldValue } }
        : rec
    ));
  };

  // Update record ID (for updates)
  const updateRecordId = (recordIndex: number, id: string) => {
    setRecords(prev => prev.map((rec, i) =>
      i === recordIndex ? { ...rec, id } : rec
    ));
  };

  // Toggle record expansion
  const toggleRecord = (index: number) => {
    setExpandedRecords(prev => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  // Filter out computed fields for editing
  const editableFields = schema?.fields.filter(f => !f.is_computed) || [];

  // Render content based on state
  const renderContent = () => {
    // Check if dependencies are not set
    if (dependsOn.length > 0) {
      const missingDeps = dependsOn.filter(dep => !fieldValues[dep]);
      if (missingDeps.length > 0) {
        return (
          <div className="px-4 py-8 text-center text-secondary">
            <AlertCircle className="mx-auto h-8 w-8 mb-2 opacity-50" />
            <p>Configure required fields to see record schema</p>
          </div>
        );
      }
    }

    // Show message when dependencies couldn't be resolved
    if (dependsOn.length > 0 && !dependenciesResolved) {
      return (
        <div className="px-4 py-8 text-center text-secondary">
          <Code className="mx-auto h-8 w-8 mb-2 opacity-50" />
          <p>Values from previous step</p>
          <p className="text-xs mt-1">Use JSON mode to configure record fields with expressions</p>
        </div>
      );
    }

    if (isLoading) {
      return (
        <div className="px-4 py-8 text-center text-secondary">
          <Loader2 className="mx-auto h-8 w-8 mb-2 animate-spin" />
          <p>Loading schema...</p>
        </div>
      );
    }

    if (error) {
      return (
        <div className="px-4 py-8 text-center text-danger">
          <AlertCircle className="mx-auto h-8 w-8 mb-2" />
          <p>{error}</p>
          <button
            type="button"
            onClick={() => { lastFetchRef.current = ''; fetchSchema(); }}
            className="mt-2 text-sm text-info hover:text-info"
          >
            Retry
          </button>
        </div>
      );
    }

    if (mode === 'json') {
      return (
        <div className="p-3">
          <textarea
            value={jsonValue}
            onChange={(e) => handleJsonChange(e.target.value)}
            className="form-input-mono h-64 resize-y"
            placeholder='[{"fields": {"Name": "value"}}]'
          />
          <p className="mt-2 text-xs text-secondary">
            Enter records as JSON array. Each record should have a &quot;fields&quot; object.
            {isUpdate && ' Include &quot;id&quot; for each record to update.'}
          </p>
        </div>
      );
    }

    // Form mode
    return (
      <div className="divide-y divide-primary">
        {records.map((record, recordIndex) => (
          <div key={recordIndex} className="bg-card">
            {/* Record header */}
            <div
              className="flex items-center gap-2 px-4 py-3 cursor-pointer hover:bg-surface /50"
              onClick={() => toggleRecord(recordIndex)}
            >
              {expandedRecords.has(recordIndex) ? (
                <ChevronDown size={16} className="text-muted" />
              ) : (
                <ChevronRight size={16} className="text-muted" />
              )}
              <span className="text-sm font-medium text-secondary">
                Record {recordIndex + 1}
              </span>
              {records.length > 1 && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); removeRecord(recordIndex); }}
                  className="ml-auto p-1 text-muted hover:text-danger transition-colors"
                  title="Remove record"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>

            {/* Record fields */}
            {expandedRecords.has(recordIndex) && (
              <div className="px-3 pb-4 space-y-4">
                {/* Record ID field for updates */}
                {isUpdate && (
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-secondary">
                      Record ID <span className="text-danger">*</span>
                    </label>
                    <input
                      type="text"
                      value={record.id || ''}
                      onChange={(e) => updateRecordId(recordIndex, e.target.value)}
                      placeholder="Enter record ID..."
                      className="form-input text-sm shadow-sm"
                    />
                  </div>
                )}

                {/* Table fields */}
                {editableFields.length > 0 ? (
                  editableFields.map((field) => (
                    <SchemaFieldInput
                      key={field.name}
                      field={field}
                      fieldValue={record.fields[field.name] || { value: '', is_expression: false }}
                      onChange={(newValue) => updateField(recordIndex, field.name, newValue)}
                    />
                  ))
                ) : (
                  <p className="text-sm text-secondary italic">
                    No editable fields found
                  </p>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Add record button */}
        {records.length < 10 && (
          <button
            type="button"
            onClick={addRecord}
            className="w-full py-3 text-secondary hover:text-secondary hover:bg-surface /50 transition-colors flex items-center justify-center gap-2"
          >
            <Plus size={16} />
            <span>Add Record</span>
          </button>
        )}
      </div>
    );
  };

  return (
    <div className="border border-primary rounded-lg overflow-hidden bg-surface">
      {/* Header with mode toggle */}
      <div className="flex items-center justify-between px-4 py-2 bg-card border-b border-primary">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-secondary">
            Records
          </span>
          {schema && (
            <span className="text-muted text-xs">
              ({schema.table_name})
            </span>
          )}
        </div>

        {/* Mode toggle */}
        <div className="flex items-center bg-input rounded text-xs overflow-hidden">
          <button
            type="button"
            onClick={() => setMode('form')}
            className={`flex items-center gap-1 px-2 py-1 transition-colors ${
              mode === 'form'
                ? 'bg-surface text-primary'
                : 'text-secondary hover:text-secondary'
            }`}
          >
            <Layout size={12} />
            Form
          </button>
          <button
            type="button"
            onClick={() => setMode('json')}
            className={`flex items-center gap-1 px-2 py-1 transition-colors ${
              mode === 'json'
                ? 'bg-surface text-primary'
                : 'text-secondary hover:text-secondary'
            }`}
          >
            <Code size={12} />
            JSON
          </button>
        </div>
      </div>

      {/* Content */}
      {renderContent()}
    </div>
  );
}
