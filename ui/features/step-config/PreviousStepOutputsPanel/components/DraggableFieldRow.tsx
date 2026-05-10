// ui/features/step-config/PreviousStepOutputsPanel/components/DraggableFieldRow.tsx

'use client';

import React from 'react';
import { TypeBadge } from './TypeBadge';

interface DragData {
  stepId: string;
  stepName: string;
  fieldName: string;
  fieldType: string;
  isArrayItem?: boolean;
  parentArray?: string;
}

interface DraggableFieldRowProps {
  fieldName: string;
  displayName: string;
  fieldType: string;
  isMapped: boolean;
  dragData: DragData;
  onClick: () => void;
  hoverClassName?: string;
  textClassName?: string;
  title?: string;
  /** Optional expand/collapse button (for array fields) */
  expandButton?: React.ReactNode;
  /** Whether this field is disabled (e.g., own-step form field) */
  disabled?: boolean;
}

/**
 * Reusable draggable field row used by SchemaView for native, prompt, and forwarded outputs.
 */
export function DraggableFieldRow({
  fieldName,
  displayName,
  fieldType,
  isMapped,
  dragData,
  onClick,
  hoverClassName = 'hover:bg-surface',
  textClassName = 'text-primary',
  title,
  expandButton,
  disabled,
}: DraggableFieldRowProps) {
  return (
    <div
      draggable={!disabled}
      onDragStart={disabled ? undefined : (e) => {
        e.dataTransfer.setData('application/x-field-mapping', JSON.stringify(dragData));
        e.dataTransfer.effectAllowed = 'copy';
      }}
      className={`py-1 pl-3 pr-1 rounded ${
        disabled
          ? 'opacity-35 cursor-default'
          : `${hoverClassName} cursor-grab active:cursor-grabbing group ${isMapped ? 'opacity-50' : ''}`
      }`}
      onClick={disabled ? undefined : onClick}
      title={title}
    >
      <div className="flex items-center gap-2">
        {expandButton}
        <TypeBadge type={fieldType} />
        <span className={`text-sm flex-1 truncate ${disabled ? 'text-muted line-through' : textClassName}`}>
          {displayName}
        </span>
        {isMapped && !disabled && (
          <span className="text-xs text-success">✓</span>
        )}
      </div>
    </div>
  );
}
