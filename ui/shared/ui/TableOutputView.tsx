// ui/shared/ui/TableOutputView.tsx

'use client';

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';
import type { OutputViewConfig, ColumnConfig } from './OutputViewRenderer';
import { TIMEOUTS } from '@/shared/lib/constants';

interface TableOutputViewProps {
  id: string;
  data: any[];
  outputView: OutputViewConfig;
  className?: string;
}

/**
 * Renders array data as a table.
 * Supports auto-detecting columns or explicit column definitions.
 */
export function TableOutputView({
  id,
  data,
  outputView,
  className = '',
}: TableOutputViewProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [copiedCell, setCopiedCell] = useState<string | null>(null);

  // Ensure data is an array
  const rows = useMemo(() => Array.isArray(data) ? data : [], [data]);

  // Compute columns
  const columns: ColumnConfig[] = useMemo(() => {
    if (outputView.columns && outputView.columns !== 'auto') {
      return outputView.columns;
    }

    // Auto-detect columns from first row
    if (rows.length === 0) return [];

    const firstRow = rows[0];
    const rowPath = outputView.row_path;

    // Get the object to extract columns from
    const sourceObj = rowPath ? getNestedValue(firstRow, rowPath) : firstRow;

    if (!sourceObj || typeof sourceObj !== 'object') return [];

    // Extract column keys
    const keys = Object.keys(sourceObj);
    return keys.map(key => ({
      key: rowPath ? `${rowPath}.${key}` : key,
      label: formatLabel(key),
    }));
  }, [rows, outputView.columns, outputView.row_path]);

  // Include ID field if specified
  const allColumns = useMemo(() => {
    const cols = [...columns];

    // Add ID column at the beginning if specified
    if (outputView.id_field && !cols.find(c => c.key === outputView.id_field)) {
      cols.unshift({ key: outputView.id_field!, label: 'ID' });
    }

    return cols;
  }, [columns, outputView.id_field]);

  const handleCopyCell = async (value: string, cellId: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedCell(cellId);
      setTimeout(() => setCopiedCell(null), TIMEOUTS.COPY_FEEDBACK);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  if (rows.length === 0) {
    return (
      <div className={`text-sm text-secondary italic ${className}`}>
        No records found
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
            Records ({rows.length})
          </span>
        </div>
      </button>

      {/* Table */}
      {isExpanded && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface border-b border-primary">
              <tr>
                {allColumns.map((col) => (
                  <th
                    key={col.key}
                    className="px-3 py-2 text-left text-xs font-medium text-secondary uppercase tracking-wider"
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-primary">
              {rows.map((row, rowIndex) => (
                <tr
                  key={row[outputView.id_field || 'id'] || rowIndex}
                  className="hover:bg-surface /50"
                >
                  {allColumns.map((col) => {
                    const value = getNestedValue(row, col.key);
                    const displayValue = formatValue(value, col.format);
                    const cellId = `${id}-${rowIndex}-${col.key}`;

                    return (
                      <td
                        key={col.key}
                        className="px-3 py-2 text-primary group relative"
                      >
                        <div className="flex items-center gap-1">
                          <span className="truncate max-w-xs" title={String(displayValue)}>
                            {displayValue}
                          </span>
                          {value && typeof value === 'string' && value.length > 0 && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleCopyCell(String(value), cellId);
                              }}
                              className="opacity-0 group-hover:opacity-100 p-1 hover:bg-input rounded transition-opacity"
                              title="Copy value"
                            >
                              {copiedCell === cellId ? (
                                <Check className="w-3 h-3 text-success" />
                              ) : (
                                <Copy className="w-3 h-3 text-muted" />
                              )}
                            </button>
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/**
 * Get nested value from object using dot notation path.
 */
function getNestedValue(obj: any, path: string): any {
  const parts = path.split('.');
  let current = obj;

  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    current = current[part]; // nosemgrep
  }

  return current;
}

/**
 * Format a key into a human-readable label.
 */
function formatLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/^./, str => str.toUpperCase());
}

/**
 * Format a value for display based on optional format hint.
 */
function formatValue(value: any, format?: string): string {
  if (value === null || value === undefined) return '-';

  if (format === 'date' && typeof value === 'string') {
    return new Date(value).toLocaleString();
  }

  if (format === 'number' && typeof value === 'number') {
    return value.toLocaleString();
  }

  if (format === 'truncate' && typeof value === 'string' && value.length > 50) {
    return value.slice(0, 50) + '...';
  }

  if (typeof value === 'object') {
    return JSON.stringify(value);
  }

  return String(value);
}

