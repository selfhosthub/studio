// ui/shared/ui/OutputViewRenderer.tsx

'use client';

import { TableOutputView } from './TableOutputView';
import { KeyValueOutputView } from './KeyValueOutputView';
import { JsonOutputView } from './JsonOutputView';

export interface FieldConfig {
  key: string;        // Dot-notation path to the value (e.g., "choices.0.message.content")
  label: string;      // Display label
  format?: 'date' | 'number' | 'truncate' | 'text';  // Optional formatting
}

export interface OutputViewConfig {
  type: 'table' | 'key_value' | 'media_grid' | 'json' | 'text';
  source?: string | null;  // Path to data in result (e.g., "records", "fields")
  row_path?: string;       // For tables: path to flatten (e.g., "fields")
  columns?: 'auto' | ColumnConfig[];
  fields?: FieldConfig[];  // For key_value: explicit fields to extract
  id_field?: string;       // Field containing row ID
  metadata_fields?: string[];  // Additional fields to show
  media_type?: 'image' | 'video';
  thumbnail_field?: string;
  download_field?: string;
  url_field?: string;
  filename_field?: string;
}

export interface ColumnConfig {
  key: string;
  label: string;
  format?: 'date' | 'number' | 'truncate';
}

interface OutputViewRendererProps {
  result: any;
  outputView?: OutputViewConfig | null;
  id: string;
  className?: string;
  /** Fallback for when there's no output_view config (uses JSON view) */
  fallbackTitle?: string;
  /** Callback for media items (images/videos) */
  onMediaClick?: (item: any) => void;
}

export function OutputViewRenderer({
  result,
  outputView,
  id,
  className = '',
  fallbackTitle = 'Output Fields',
  onMediaClick,
}: OutputViewRendererProps) {
  if (!result) {
    return (
      <div className={`text-sm text-secondary italic ${className}`}>
        No result data
      </div>
    );
  }

  if (!outputView) {
    return (
      <JsonOutputView
        id={id}
        title={fallbackTitle}
        data={result}
      />
    );
  }

  const data = outputView.source ? getNestedValue(result, outputView.source) : result;

  switch (outputView.type) {
    case 'table':
      return (
        <TableOutputView
          id={id}
          data={data}
          outputView={outputView}
          className={className}
        />
      );

    case 'key_value':
      return (
        <KeyValueOutputView
          id={id}
          data={data}
          outputView={outputView}
          className={className}
        />
      );

    case 'media_grid':
      return (
        <JsonOutputView
          id={id}
          title="Media Output"
          data={data}
        />
      );

    case 'text':
      return (
        <div className={`prose dark:prose-invert max-w-none ${className}`}>
          <p className="whitespace-pre-wrap">{String(data)}</p>
        </div>
      );

    case 'json':
    default:
      return (
        <JsonOutputView
          id={id}
          title={fallbackTitle}
          data={data}
        />
      );
  }
}

function getNestedValue(obj: any, path: string): any {
  const parts = path.split('.');
  let current = obj;

  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    current = current[part]; // nosemgrep
  }

  return current;
}
