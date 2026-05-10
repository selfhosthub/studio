// ui/shared/ui/KeyValueOutputView.tsx

'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';
import type { OutputViewConfig, FieldConfig } from './OutputViewRenderer';
import { TIMEOUTS } from '@/shared/lib/constants';

interface KeyValueOutputViewProps {
  id: string;
  data: any;
  outputView: OutputViewConfig;
  className?: string;
}

/**
 * Renders an object as a key-value list.
 * Useful for displaying single records.
 */
export function KeyValueOutputView({
  id,
  data,
  outputView,
  className = '',
}: KeyValueOutputViewProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Get the entries to display
  // If explicit fields are configured, use those with nested path extraction
  // Otherwise, fall back to displaying all top-level keys
  const entries: [string, any][] = (() => {
    if (outputView.fields && outputView.fields.length > 0) {
      // Extract explicit fields using dot-notation paths
      return outputView.fields.map((field: FieldConfig) => {
        const value = getNestedValue(data, field.key);
        return [field.label, value];
      });
    }
    // Fall back to object entries
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      return Object.entries(data);
    }
    return [];
  })();

  const handleCopy = async (value: string, key: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), TIMEOUTS.COPY_FEEDBACK);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  if (entries.length === 0) {
    return (
      <div className={`text-sm text-secondary italic ${className}`}>
        No data available
      </div>
    );
  }

  return (
    <div className={`border border-primary rounded-lg overflow-hidden ${className}`}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 bg-surface hover:bg-card transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-secondary" />
          ) : (
            <ChevronRight className="w-4 h-4 text-secondary" />
          )}
          <span className="text-sm font-medium text-secondary">
            Output Fields ({entries.length})
          </span>
        </div>
      </button>

      {/* Key-Value List */}
      {isExpanded && (
        <dl className="divide-y divide-primary">
          {entries.map(([key, value]) => (
            <div
              key={key}
              className="px-3 py-2 grid grid-cols-3 gap-4 group hover:bg-surface /50"
            >
              <dt className="text-sm font-medium text-secondary">
                {formatLabel(key)}
              </dt>
              <dd className="text-sm text-primary col-span-2 flex items-center gap-2">
                <span className="truncate" title={formatDisplayValue(value)}>
                  {formatDisplayValue(value)}
                </span>
                {value && typeof value === 'string' && value.length > 0 && (
                  <button
                    onClick={() => handleCopy(String(value), key)}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-input rounded transition-opacity flex-shrink-0"
                    title="Copy value"
                  >
                    {copiedKey === key ? (
                      <Check className="w-3 h-3 text-success" />
                    ) : (
                      <Copy className="w-3 h-3 text-muted" />
                    )}
                  </button>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

/**
 * Get nested value from object using dot notation path.
 * Supports array indices (e.g., "choices.0.message.content")
 */
function getNestedValue(obj: any, path: string): any {
  if (!path || !obj) return obj;

  const parts = path.split('.');
  let current = obj;

  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    current = current[part]; // nosemgrep
  }

  return current;
}

/**
 * Common field name mappings for better display labels.
 */
const FIELD_LABEL_MAPPINGS: Record<string, string> = {
  'downloaded_files': 'Generated Files',
  'downloaded_file': 'Generated File',
  'output_files': 'Output Files',
  'output_file': 'Output File',
  'image_count': 'Images Generated',
  'seed_used': 'Seed Used',
  'prompt_id': 'Execution ID',
};

/**
 * Format a key into a human-readable label.
 */
function formatLabel(key: string): string {
  // Check for explicit mapping first
  if (FIELD_LABEL_MAPPINGS[key]) {
    return FIELD_LABEL_MAPPINGS[key];
  }
  // Fall back to auto-formatting
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/^./, str => str.toUpperCase());
}

/**
 * Format a value for display.
 */
function formatDisplayValue(value: any): string {
  if (value === null || value === undefined) return '-';

  if (typeof value === 'boolean') return value ? 'Yes' : 'No';

  if (typeof value === 'object') {
    if (Array.isArray(value)) {
      // For small arrays of primitives, show actual values
      if (value.length <= 10) {
        const allPrimitives = value.every(
          v => typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'
        );
        if (allPrimitives) {
          return value.join(', ');
        }
      }
      return `[${value.length} items]`;
    }
    return JSON.stringify(value);
  }

  return String(value);
}

