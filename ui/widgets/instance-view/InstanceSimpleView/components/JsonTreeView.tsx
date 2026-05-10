// ui/widgets/instance-view/InstanceSimpleView/components/JsonTreeView.tsx

'use client';

import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { ChevronDown, ChevronRight, Copy, CheckCircle2, Pencil, X, Check, RotateCcw, Info } from 'lucide-react';
import { TIMEOUTS } from '@/shared/lib/constants';

interface JsonTreeViewProps {
  id: string;
  title: string;
  data: any;
  fallbackText: string;
  description?: string;
  editable?: boolean;
  onSave?: (data: any) => void;
  saving?: boolean;
}

interface TreeNodeProps {
  keyName: string | number | null;
  value: any;
  path: (string | number)[];
  depth: number;
  editable: boolean;
  editedPaths: Set<string>;
  onEdit: (path: (string | number)[], newValue: any) => void;
}

function getValueType(value: any): 'string' | 'number' | 'boolean' | 'null' | 'array' | 'object' {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value as 'string' | 'number' | 'boolean' | 'object';
}

function getValueColor(type: string): string { // css-check-ignore -- JSON syntax highlighting
  switch (type) {
    case 'string': return 'text-success';
    case 'number': return 'text-info';
    case 'boolean': return 'text-purple-600 dark:text-purple-400';
    case 'null': return 'text-muted';
    default: return 'text-primary';
  }
}

function InlineEditor({
  value,
  type,
  onSave,
  onCancel
}: {
  value: any;
  type: string;
  onSave: (value: any) => void;
  onCancel: () => void;
}) {
  const [editValue, setEditValue] = useState(() => {
    if (type === 'string') return value;
    if (type === 'null') return '';
    return JSON.stringify(value);
  });
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const handleSave = () => {
    try {
      let parsed: any;
      if (type === 'string') {
        parsed = editValue;
      } else if (type === 'number') {
        parsed = parseFloat(editValue);
        if (isNaN(parsed)) return;
      } else if (type === 'boolean') {
        parsed = editValue.toLowerCase() === 'true';
      } else if (type === 'null' && editValue === '') {
        parsed = null;
      } else {
        parsed = JSON.parse(editValue);
      }
      onSave(parsed);
    } catch {
      // Invalid JSON, don't save
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      onCancel();
    }
  };

  return (
    <span className="inline-flex items-center gap-1">
      <input
        ref={inputRef}
        type="text"
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onKeyDown={handleKeyDown}
        className="px-1 py-0.5 text-xs border border-info rounded bg-card text-primary focus:outline-none focus:ring-1 focus:ring-info min-w-[60px]"
        style={{ width: `${Math.max(60, editValue.length * 8)}px` }}
      />
      <button
        onClick={handleSave}
        className="p-0.5 text-success hover:text-success"
        title="Save"
      >
        <Check className="w-3 h-3" />
      </button>
      <button
        onClick={onCancel}
        className="p-0.5 text-danger hover:text-danger"
        title="Cancel"
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}

export function TreeNode({ keyName, value, path, depth, editable, editedPaths, onEdit }: TreeNodeProps) {
  const [isExpanded, setIsExpanded] = useState(depth < 2); // Auto-expand first 2 levels
  const [isEditing, setIsEditing] = useState(false);
  const type = getValueType(value);
  const isExpandable = type === 'object' || type === 'array';
  const pathString = path.join('.');
  const isEdited = editedPaths.has(pathString);

  const handleEditSave = (newValue: any) => {
    onEdit(path, newValue);
    setIsEditing(false);
  };

  const renderValue = () => {
    if (isEditing && !isExpandable) {
      return (
        <InlineEditor
          value={value}
          type={type}
          onSave={handleEditSave}
          onCancel={() => setIsEditing(false)}
        />
      );
    }

    if (type === 'string') {
      return (
        <span className={`${getValueColor(type)} ${isEdited ? 'bg-warning-subtle px-1 rounded' : ''}`}>
          &quot;{value}&quot;
        </span>
      );
    }
    if (type === 'null') {
      return <span className={getValueColor(type)}>null</span>;
    }
    if (type === 'boolean') {
      return <span className={`${getValueColor(type)} ${isEdited ? 'bg-warning-subtle px-1 rounded' : ''}`}>{String(value)}</span>;
    }
    if (type === 'number') {
      return <span className={`${getValueColor(type)} ${isEdited ? 'bg-warning-subtle px-1 rounded' : ''}`}>{value}</span>;
    }
    if (type === 'array') {
      return <span className="text-secondary">[{value.length}]</span>;
    }
    if (type === 'object') {
      const keys = Object.keys(value);
      return <span className="text-secondary">{`{${keys.length}}`}</span>;
    }
    return null;
  };

  const renderChildren = () => {
    if (!isExpandable || !isExpanded) return null;

    const entries = type === 'array'
      ? value.map((v: any, i: number) => [i, v] as const)
      : Object.entries(value);

    return (
      <div className="ml-4 border-l border-primary pl-2">
        {entries.map(([key, val]: [string | number, any]) => (
          <TreeNode
            key={key}
            keyName={key}
            value={val}
            path={[...path, key]}
            depth={depth + 1}
            editable={editable}
            editedPaths={editedPaths}
            onEdit={onEdit}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="text-xs font-mono">
      <div className="flex items-center gap-1 py-0.5 hover:bg-surface /50 rounded group">
        {isExpandable ? (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-0.5 hover:bg-input rounded flex-shrink-0"
          >
            {isExpanded ? (
              <ChevronDown className="w-3 h-3 text-muted" />
            ) : (
              <ChevronRight className="w-3 h-3 text-muted" />
            )}
          </button>
        ) : (
          <span className="w-4" /> // Spacer for alignment
        )}

        {keyName !== null && (
          <span className="text-secondary">
            {typeof keyName === 'number' ? `[${keyName}]` : `${keyName}`}:
          </span>
        )}

        <span className="flex-1">{renderValue()}</span>

        {/* Edit button for non-expandable values */}
        {editable && !isExpandable && !isEditing && (
          <button
            onClick={() => setIsEditing(true)}
            className="p-0.5 opacity-0 group-hover:opacity-100 text-muted hover:text-info transition-opacity"
            title="Edit value"
          >
            <Pencil className="w-3 h-3" />
          </button>
        )}
      </div>
      {renderChildren()}
    </div>
  );
}

/**
 * JSON Tree View component with collapsible nodes and optional editing
 */
export function JsonTreeView({
  id,
  title,
  data,
  fallbackText,
  description,
  editable = false,
  onSave,
  saving = false,
}: JsonTreeViewProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [copiedJson, setCopiedJson] = useState<string | null>(null);
  const [editedData, setEditedData] = useState<any>(null);
  const [editedPaths, setEditedPaths] = useState<Set<string>>(new Set());

  const hasData = data && (typeof data === 'object' ? Object.keys(data).length > 0 : true);
  const hasEdits = editedPaths.size > 0;
  const displayData = editedData ?? data;

  const handleCopyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(displayData, null, 2));
      setCopiedJson(id);
      setTimeout(() => setCopiedJson(null), TIMEOUTS.COPY_FEEDBACK);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  const handleEdit = useCallback((path: (string | number)[], newValue: any) => {
    setEditedData((prev: any) => {
      const base = prev ?? JSON.parse(JSON.stringify(data));
      let current = base;
      for (let i = 0; i < path.length - 1; i++) {
        current = current[path[i]]; // nosemgrep
      }
      current[path[path.length - 1]] = newValue;
      return base;
    });
    setEditedPaths(prev => new Set(prev).add(path.join('.')));
  }, [data]);

  const handleSave = () => {
    if (onSave && editedData) {
      onSave(editedData);
    }
  };

  const handleReset = () => {
    setEditedData(null);
    setEditedPaths(new Set());
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
          {description && (
            <span title={description}>
              <Info
                className="w-3.5 h-3.5 text-muted hover:text-secondary cursor-help"
              />
            </span>
          )}
          {hasEdits && (
            <span className="text-xs px-1.5 py-0.5 bg-warning-subtle text-warning rounded">
              Modified
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
              <div className="overflow-auto max-h-[60vh]">
                <TreeNode
                  keyName={null}
                  value={displayData}
                  path={[]}
                  depth={0}
                  editable={editable}
                  editedPaths={editedPaths}
                  onEdit={handleEdit}
                />
              </div>
              {editable && hasEdits && (
                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-primary">
                  <button
                    onClick={handleSave}
                    disabled={saving}
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
                  <span className="text-xs text-secondary">
                    {editedPaths.size} field{editedPaths.size !== 1 ? 's' : ''} modified
                  </span>
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

export default JsonTreeView;
