// ui/features/form-field-renderer/fields/JsonField.tsx

'use client';

import React, { useMemo, useState } from 'react';
import type { FormFieldConfig } from '@/entities/workflow';

interface Props {
  config: FormFieldConfig;
  value: unknown;
  onChange: (next: string) => void;
  /** Validation error from the form-level validator (e.g. required). */
  error?: string;
}

/**
 * JSON-editing textarea for the instance form. Stores the raw string in
 * parent state (form_values is string-keyed; the worker coerces on the
 * way out) but provides live JSON validation feedback so the user knows
 * mid-edit when their input wouldn't parse - without snapping their
 * typing back. The validator runs purely on the local buffer; parent
 * onChange always fires with the raw text so existing form-state
 * plumbing (which expects a string for json fields) is unchanged.
 */
export function JsonField({ config, value, onChange, error }: Props) {
  const display = useMemo(
    () => (typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2)),
    [value],
  );
  // Track parse state for visual feedback. Empty buffer = valid (form-
  // level "required" validation handles emptiness separately).
  const [parseError, setParseError] = useState(false);

  const validate = (raw: string) => {
    if (raw.trim() === '') {
      setParseError(false);
      return;
    }
    try {
      JSON.parse(raw);
      setParseError(false);
    } catch {
      setParseError(true);
    }
  };

  const showDanger = parseError || Boolean(error);

  return (
    <div>
      <textarea
        className={`form-input font-mono text-sm${showDanger ? ' border-danger' : ''}`}
        rows={6}
        value={display}
        onChange={(e) => {
          const next = e.target.value;
          validate(next);
          onChange(next);
        }}
        onBlur={(e) => validate(e.target.value)}
        placeholder={config.placeholder || '{\n  "key": "value"\n}'}
        spellCheck={false}
      />
      {parseError && !error && (
        <p className="mt-1 text-xs text-danger">
          Invalid JSON - fix before submitting.
        </p>
      )}
    </div>
  );
}
