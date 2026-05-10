// ui/features/step-config/ui/output-fields/BaseOutputFieldList.tsx

'use client';

import React from 'react';
import BaseOutputFieldItem from './BaseOutputFieldItem';

interface BaseOutputFieldListProps {
  fields: Record<string, {
    path: string;
    description?: string;
    type?: string;
  }>;
  onUpdate: (fieldKey: string, updatedField: any) => void;
  onRemove: (fieldKey: string) => void;
  collapsedItems: string[];
  onToggleCollapse: (fieldKey: string) => void;
  className?: string;
  typeOptions?: { value: string; label: string }[];
}

export default function BaseOutputFieldList({
  fields,
  onUpdate,
  onRemove,
  collapsedItems,
  onToggleCollapse,
  className = '',
  typeOptions
}: BaseOutputFieldListProps) {
  return (
    <div className={`space-y-3${className}`}>
      {Object.entries(fields).map(([key, field]) => (
        <BaseOutputFieldItem
          key={key}
          fieldKey={key}
          field={field}
          isCollapsed={collapsedItems.includes(key)}
          onUpdate={onUpdate}
          onRemove={onRemove}
          onToggleCollapse={onToggleCollapse}
          typeOptions={typeOptions}
        />
      ))}
    </div>
  );
}