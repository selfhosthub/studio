// ui/features/step-config/MappableParameterField/components/KeyValueEditor.tsx

'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Plus, X } from 'lucide-react';

interface KeyValueEditorProps {
  value: Record<string, string> | undefined;
  onChange: (next: Record<string, string>) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  addLabel?: string;
}

interface Row {
  id: number;
  key: string;
  value: string;
}

/**
 * Stacked two-input editor for string→string object fields.
 *
 * Emits a plain object like `{"wrong": "correct", ...}`. Internal row state
 * is kept so the user can type multi-word keys and trailing spaces without
 * losing focus or content; the emitted dict strips empty-key rows and trims
 * whitespace only at the commit boundary.
 */
export function KeyValueEditor({
  value,
  onChange,
  keyPlaceholder = 'key',
  valuePlaceholder = 'value',
  addLabel = 'Add pair',
}: KeyValueEditorProps) {
  // Row IDs are derived from a monotonic counter. Seeded rows claim the
  // first N IDs deterministically; the ref takes over from there in
  // handlers (post-render) so we never touch .current during render.
  const [rows, setRows] = useState<Row[]>(() => {
    const seeded = value
      ? Object.entries(value).map(([k, v], i) => ({ id: i, key: k, value: v }))
      : [];
    return [...seeded, { id: seeded.length, key: '', value: '' }];
  });
  const nextId = useRef(rows.length);

  // When the parent value changes from outside (reset / programmatic), re-sync
  // local rows. Heuristic: skip re-sync when our own emit produced the change,
  // which we detect by comparing trimmed local state to the incoming value.
  const lastEmitted = useRef<Record<string, string>>(toDict(rows));
  useEffect(() => {
    const incoming = value ?? {};
    if (JSON.stringify(incoming) === JSON.stringify(lastEmitted.current)) return;
    const seeded = Object.entries(incoming).map(([k, v]) => ({
      id: nextId.current++,
      key: k,
      value: v,
    }));
    setRows([...seeded, { id: nextId.current++, key: '', value: '' }]);
    lastEmitted.current = incoming;
  }, [value]);

  function toDict(current: Row[]): Record<string, string> {
    const dict: Record<string, string> = {};
    for (const row of current) {
      const k = row.key.trim();
      if (k) dict[k] = row.value;
    }
    return dict;
  }

  const commit = (next: Row[]) => {
    setRows(next);
    const dict = toDict(next);
    lastEmitted.current = dict;
    onChange(dict);
  };

  const updateRow = (id: number, field: 'key' | 'value', next: string) => {
    const working = rows.map((row) =>
      row.id === id ? { ...row, [field]: next } : row
    );
    commit(working);
  };

  const removeRow = (id: number) => {
    const working = rows.filter((row) => row.id !== id);
    if (working.length === 0) {
      working.push({ id: nextId.current++, key: '', value: '' });
    }
    commit(working);
  };

  const addRow = () => {
    const working = [...rows, { id: nextId.current++, key: '', value: '' }];
    commit(working);
  };

  return (
    <div className="w-full min-w-0 space-y-2">
      {rows.map((row, index) => {
        const isTrailing = index === rows.length - 1 && !row.key && !row.value;
        return (
          <div key={row.id} className="flex gap-2 items-center min-w-0 overflow-hidden">
            <input
              type="text"
              value={row.key}
              onChange={(e) => updateRow(row.id, 'key', e.target.value)}
              placeholder={keyPlaceholder}
              className="flex-1 w-0 min-w-0 px-2 py-1.5 border rounded text-sm"
            />
            <span className="text-muted text-sm">→</span>
            <input
              type="text"
              value={row.value}
              onChange={(e) => updateRow(row.id, 'value', e.target.value)}
              placeholder={valuePlaceholder}
              className="flex-1 w-0 min-w-0 px-2 py-1.5 border rounded text-sm"
            />
            <button
              type="button"
              onClick={() => removeRow(row.id)}
              className={`p-1 text-danger hover:bg-danger-subtle rounded ${isTrailing ? 'invisible' : ''}`}
              title="Remove pair"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
      <button
        type="button"
        onClick={addRow}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-info hover:bg-info-subtle rounded border border-dashed border-info"
      >
        <Plus size={14} />
        {addLabel}
      </button>
    </div>
  );
}

export default KeyValueEditor;
