// ui/widgets/instance-view/InstanceSimpleView/components/JsonRawEditor.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Copy, CheckCircle2, Check, RotateCcw } from 'lucide-react';
import { TIMEOUTS } from '@/shared/lib/constants';

interface JsonRawEditorProps {
  id: string;
  title: string;
  data: any;
  fallbackText: string;
  editable?: boolean;
  onSave?: (data: any) => void;
  saving?: boolean;
}

/**
 * Raw JSON editor component with textarea editing
 */
export function JsonRawEditor({
  id,
  title,
  data,
  fallbackText,
  editable = false,
  onSave,
  saving = false,
}: JsonRawEditorProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [copiedJson, setCopiedJson] = useState<string | null>(null);
  const [editedText, setEditedText] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  const hasData = data && (typeof data === 'object' ? Object.keys(data).length > 0 : true);
  const originalText = JSON.stringify(data, null, 2);
  const displayText = editedText ?? originalText;
  const hasEdits = editedText !== null && editedText !== originalText;

  // Validate JSON on edit
  useEffect(() => {
    if (editedText === null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setParseError(null);
      return;
    }
    try {
      JSON.parse(editedText);
      setParseError(null);
    } catch (e: unknown) {
      setParseError(e instanceof Error ? e.message : 'Invalid JSON');
    }
  }, [editedText]);

  const handleCopyJson = async () => {
    try {
      await navigator.clipboard.writeText(displayText);
      setCopiedJson(id);
      setTimeout(() => setCopiedJson(null), TIMEOUTS.COPY_FEEDBACK);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  const handleSave = async () => {
    if (!onSave || !editedText || parseError) return;
    try {
      const parsed = JSON.parse(editedText);
      await onSave(parsed);
      setEditedText(null); // Reset after successful save
    } catch {
      // Parse error already shown
    }
  };

  const handleReset = () => {
    setEditedText(null);
    setParseError(null);
  };

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <div className="border border-primary rounded-lg overflow-hidden">
      <div
        role="button"
        tabIndex={0}
        onClick={toggleExpanded}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpanded(); } }}
        className="w-full flex items-center justify-between px-3 py-2 bg-surface hover:bg-card transition-colors cursor-pointer"
      >
        <span className="text-sm font-medium text-secondary flex items-center gap-2">
          {title}
          {hasEdits && (
            <span className="text-xs px-1.5 py-0.5 bg-warning-subtle text-warning rounded">
              Modified
            </span>
          )}
          {parseError && (
            <span className="text-xs px-1.5 py-0.5 bg-danger-subtle text-danger rounded">
              Invalid JSON
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
          {hasData && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleCopyJson();
              }}
              className="p-1 hover:bg-input rounded"
              title="Copy JSON"
            >
              {copiedJson === id ? (
                <CheckCircle2 className="w-4 h-4 text-success" />
              ) : (
                <Copy className="w-4 h-4 text-muted" />
              )}
            </button>
          )}
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-muted" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted" />
          )}
        </div>
      </div>
      {isExpanded && (
        <div className="p-3 bg-card">
          {hasData ? (
            <>
              {editable ? (
                <textarea
                  value={displayText}
                  onChange={(e) => setEditedText(e.target.value)}
                  className={`w-full h-80 p-2 text-xs font-mono bg-surface border rounded resize-y focus:outline-none focus:ring-1 ${
                    parseError
                      ? 'border-danger focus:ring-[var(--theme-danger)]'
                      : 'border-primary focus:ring-[var(--theme-primary)]'
                  } text-primary`}
                  spellCheck={false}
                />
              ) : (
                <pre className="text-xs overflow-auto max-h-80 text-primary font-mono">
                  {displayText}
                </pre>
              )}
              {parseError && (
                <p className="mt-2 text-xs text-danger">
                  {parseError}
                </p>
              )}
              {editable && hasEdits && !parseError && (
                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-primary">
                  <button
                    onClick={handleSave}
                    disabled={saving || !!parseError}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm btn-primary disabled:opacity-50"
                  >
                    {saving ? (
                      <>
                        <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Saving...
                      </>
                    ) : (
                      <>
                        <Check className="w-3.5 h-3.5" />
                        Save Changes
                      </>
                    )}
                  </button>
                  <button
                    onClick={handleReset}
                    disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-secondary hover:text-primary"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    Reset
                  </button>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted dark:text-secondary italic">{fallbackText}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default JsonRawEditor;
