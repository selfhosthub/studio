// ui/features/step-config/MappableParameterField/components/FieldInput.tsx

'use client';

import React, { useEffect, useState } from 'react';
import { UserFilePicker } from '@/features/files';
import { ColorPickerModal } from './ColorPickerModal';
import { KeyValueEditor } from './KeyValueEditor';
import { OMIT_SENTINEL } from '@/shared/lib/constants';
import type { PropertySchema } from '../types';

export type FieldInputSize = 'default' | 'compact';

export type FieldInputMediaHint = 'image' | 'video' | 'audio' | 'all';

interface FieldInputProps {
  schema: PropertySchema;
  value: any;
  onChange: (value: any) => void;
  size?: FieldInputSize;
  /** Used to infer URI picker media type when uriMediaHint is not provided. */
  paramKey?: string;
  /** Explicit media hint for URI picker (overrides name-based inference). */
  uriMediaHint?: FieldInputMediaHint;
  /** Inherited color shown in the color picker when value is empty. */
  colorFallback?: string;
  /** Label used to build the empty-option prompt for required enums. */
  label?: string;
  /** When true, required enums display a "Select …" placeholder option. */
  required?: boolean;
}

const CLASSES: Record<FieldInputSize, {
  input: string;
  inputMono: string;
  textareaDefaultRows: number;
  checkboxSpan: string;
  checkboxLabel: string;
}> = {
  default: {
    input: 'flex-1 min-w-0 w-full p-2 border rounded text-sm',
    inputMono: 'flex-1 min-w-0 w-full p-2 border rounded font-mono text-sm',
    textareaDefaultRows: 3,
    checkboxSpan: 'text-sm text-secondary',
    checkboxLabel: 'flex items-center gap-2 flex-1 min-w-0',
  },
  compact: {
    input: 'w-full min-w-0 p-1.5 border rounded text-sm',
    inputMono: 'w-full min-w-0 p-1.5 border rounded font-mono text-xs',
    textareaDefaultRows: 2,
    checkboxSpan: 'text-xs text-secondary',
    checkboxLabel: 'flex items-center gap-2 min-w-0',
  },
};

function inferUriMediaHint(paramKey: string | undefined, title: string | undefined): FieldInputMediaHint {
  const nameLower = (paramKey || '').toLowerCase();
  const titleLower = (title || '').toLowerCase();
  if (nameLower.includes('image') || titleLower.includes('image')) return 'image';
  if (nameLower.includes('video') || titleLower.includes('video')) return 'video';
  if (nameLower.includes('audio') || titleLower.includes('audio')) return 'audio';
  return 'all';
}

/**
 * Editable JSON textarea for `type: "object"` fields.
 *
 * Maintains a local string buffer so the user can type freely through
 * intermediate invalid-JSON states (e.g. after typing "{") without their
 * input snapping back. Parent `onChange` only fires when the buffer
 * parses cleanly as JSON - partial/invalid input is held locally until
 * it becomes valid. The buffer re-syncs from external value changes only
 * when the textarea is not focused, so an outside reset doesn't clobber
 * mid-edit content but still propagates legitimate updates.
 *
 * Visual feedback: when the buffer doesn't parse, the textarea border is
 * danger-colored and a small "Invalid JSON" hint shows below - so the
 * user knows their input isn't being persisted yet without their typing
 * being silently swallowed.
 */
function ObjectJsonTextarea({
  value,
  onChange,
  classes,
}: {
  value: any;
  onChange: (next: any) => void;
  classes: { inputMono: string; textareaDefaultRows: number };
}) {
  const externalText = React.useMemo(() => {
    if (value && typeof value === 'object') return JSON.stringify(value, null, 2);
    if (typeof value === 'string') return value;
    return '';
  }, [value]);

  const [text, setText] = useState<string>(externalText);
  const [isFocused, setIsFocused] = useState(false);
  const [parseError, setParseError] = useState(false);

  // Sync the buffer from the parent only when the textarea isn't focused -
  // prevents a parent re-render (e.g. another field changing) from
  // clobbering the user's mid-edit content.
  useEffect(() => {
    if (!isFocused && externalText !== text) {
      setText(externalText);
      setParseError(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalText, isFocused]);

  return (
    <div className="flex-1 w-full flex flex-col">
      <textarea
        value={text}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        onChange={(e) => {
          const next = e.target.value;
          setText(next);
          if (next === '') {
            setParseError(false);
            onChange({});
            return;
          }
          try {
            const parsed = JSON.parse(next);
            setParseError(false);
            onChange(parsed);
          } catch {
            // Invalid mid-typing - hold the buffer locally and flag the
            // visual error state. Parent stays at its last-valid value
            // until the user's input parses cleanly.
            setParseError(true);
          }
        }}
        className={`w-full p-2 border rounded font-mono text-sm${parseError ? ' border-danger' : ''}`}
        rows={classes.textareaDefaultRows}
        placeholder={'{"key": "value"}'}
        spellCheck={false}
      />
      {parseError && (
        <p className="mt-1 text-xs text-danger">
          Invalid JSON - value will be saved once parsing succeeds.
        </p>
      )}
    </div>
  );
}

/**
 * Shared input renderer for schema-driven form fields. Handles the widget
 * branches common to top-level step params (StaticInputRenderer) and
 * fields inside array items (ArrayItemsPanel). Specialised widgets
 * (resolution picker, date picker, dynamic combobox, nested arrays)
 * stay in their respective callers because they need extra context.
 */
export function FieldInput({
  schema,
  value,
  onChange,
  size = 'default',
  paramKey,
  uriMediaHint,
  colorFallback,
  label,
  required,
}: FieldInputProps) {
  const classes = CLASSES[size];
  const hasEnum = schema.enum && schema.enum.length > 0;
  const isNumeric = schema.type === 'number' || schema.type === 'integer';
  const [sentinelWarning, setSentinelWarning] = React.useState(false);

  // Reserved word guard: `__omit__` is a request-builder sentinel; block it
  // as a literal user value so the field doesn't silently drop from the
  // rendered request body.
  const guardSentinel = (next: any): any => {
    if (typeof next === 'string' && next.trim() === OMIT_SENTINEL) {
      setSentinelWarning(true);
      return value ?? '';
    }
    if (sentinelWarning) setSentinelWarning(false);
    return next;
  };
  const guardedOnChange = (next: any) => onChange(guardSentinel(next));

  if (hasEnum) {
    const enumHasEmpty = schema.enum!.includes('');
    const showEmptyOption = !enumHasEmpty && schema.default === undefined;
    const emptyLabel = required && label ? `Select ${label.toLowerCase()}...` : '';
    return (
      <select
        value={value ?? schema.default ?? ''}
        onChange={(e) => {
          const raw = e.target.value;
          const enumValue = schema.enum?.find(v => String(v) === raw);
          onChange(enumValue !== undefined ? enumValue : raw);
        }}
        className={classes.input}
      >
        {showEmptyOption && <option value="">{emptyLabel}</option>}
        {schema.enum!.map((ev, idx) => (
          <option key={String(ev)} value={String(ev)}>
            {schema.enumNames?.[idx] ?? String(ev)}
          </option>
        ))}
      </select>
    );
  }

  if (schema.type === 'boolean') {
    return (
      <label className={classes.checkboxLabel}>
        <input
          type="checkbox"
          checked={value ?? schema.default ?? false}
          onChange={(e) => onChange(e.target.checked)}
          className="h-4 w-4 text-info border-primary rounded"
        />
        <span className={classes.checkboxSpan}>{schema.description || 'Enable'}</span>
      </label>
    );
  }

  if (schema.type === 'object') {
    if (schema.ui?.widget === 'key-value') {
      return (
        <KeyValueEditor
          value={value && typeof value === 'object' ? value : {}}
          onChange={onChange}
          keyPlaceholder={schema.ui?.keyPlaceholder}
          valuePlaceholder={schema.ui?.valuePlaceholder}
          addLabel={schema.ui?.addLabel}
        />
      );
    }
    return (
      <ObjectJsonTextarea
        value={value}
        onChange={onChange}
        classes={classes}
      />
    );
  }

  if (isNumeric) {
    const displayValue = value === '' ? '' : (value ?? schema.default ?? '');
    return (
      <input
        type="number"
        value={displayValue}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === '') { onChange(''); return; }
          const n = schema.type === 'integer' ? parseInt(raw, 10) : parseFloat(raw);
          onChange(isNaN(n) ? undefined : n);
        }}
        step={schema.type === 'integer' ? 1 : 'any'}
        min={schema.minimum}
        max={schema.maximum}
        className={classes.input}
      />
    );
  }

  if (schema.format === 'color') {
    return (
      <ColorPickerModal
        value={value ?? schema.default ?? (colorFallback ? '' : '#000000')}
        onChange={onChange}
        placeholderColor={colorFallback}
      />
    );
  }

  if (schema.format === 'uri') {
    const mediaTypeFilter = uriMediaHint ?? inferUriMediaHint(paramKey, schema.title);
    return (
      <UserFilePicker
        value={value ?? schema.default ?? ''}
        onChange={onChange}
        mediaTypeFilter={mediaTypeFilter}
        placeholder={schema.ui?.placeholder || schema.description || 'Enter URL or select file...'}
      />
    );
  }

  if (schema.ui?.widget === 'textarea' || schema.format === 'textarea') {
    return (
      <div className="param-field-input-wrap">
        <textarea
          value={value ?? schema.default ?? ''}
          onChange={(e) => guardedOnChange(e.target.value)}
          className={classes.input}
          rows={schema.ui?.rows ?? classes.textareaDefaultRows}
          placeholder={schema.ui?.placeholder}
        />
        {sentinelWarning && (
          <p className="text-xs text-danger mt-1">
            {`"${OMIT_SENTINEL}" is a reserved word and cannot be used as a value.`}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="param-field-input-wrap">
      <input
        type={schema.format === 'password' ? 'password' : 'text'}
        value={value ?? schema.default ?? ''}
        onChange={(e) => guardedOnChange(e.target.value)}
        minLength={schema.minLength}
        maxLength={schema.maxLength}
        className={classes.input}
        placeholder={schema.ui?.placeholder || schema.description}
      />
      {sentinelWarning && (
        <p className="text-xs text-danger mt-1">
          {`"${OMIT_SENTINEL}" is a reserved word and cannot be used as a value.`}
        </p>
      )}
    </div>
  );
}
