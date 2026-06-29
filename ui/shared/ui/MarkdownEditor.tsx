// ui/shared/ui/MarkdownEditor.tsx

'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownEditorProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
}

export function MarkdownEditor({ id, value, onChange, placeholder, rows = 20 }: MarkdownEditorProps) {
  const [showPreview, setShowPreview] = useState(false);

  return (
    <div className="space-y-2">
      {/* Toggle buttons */}
      <div className="flex border border-primary rounded-md w-fit">
        <button
          type="button"
          onClick={() => setShowPreview(false)}
          className={`px-4 py-1.5 text-sm font-medium rounded-l-md transition-colors ${
            !showPreview ? 'toggle-btn-active' : 'toggle-btn-inactive'
          }`}
        >
          Edit
        </button>
        <button
          type="button"
          onClick={() => setShowPreview(true)}
          className={`px-4 py-1.5 text-sm font-medium rounded-r-md transition-colors ${
            showPreview ? 'toggle-btn-active' : 'toggle-btn-inactive'
          }`}
        >
          Preview
        </button>
      </div>

      {/* Editor or Preview */}
      {showPreview ? (
        <div className="card-section min-h-[400px] overflow-auto">
          {value ? (
            <div className="prose prose-sm dark:prose-invert max-w-none prose-semantic-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-muted italic">No content to preview</p>
          )}
        </div>
      ) : (
        <textarea
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={rows}
          className="form-textarea font-mono text-sm"
          placeholder={placeholder}
        />
      )}
    </div>
  );
}
