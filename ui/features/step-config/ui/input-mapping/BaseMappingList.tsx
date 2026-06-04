// ui/features/step-config/ui/input-mapping/BaseMappingList.tsx

'use client';

import React from 'react';
import BaseMappingItem from './BaseMappingItem';
import { Step } from '@/entities/workflow';

interface BaseMappingListProps {
  mappings: Record<string, {
    source_step_id: string;
    source_output_field: string;
    transform?: string;
  }>;
  previousSteps: Step[];
  onUpdate: (mappingKey: string, updatedMapping: any) => void;
  onRemove: (mappingKey: string) => void;
  collapsedItems: string[];
  onToggleCollapse: (mappingKey: string) => void;
  className?: string;
  showTransform?: boolean;
}

export default function BaseMappingList({
  mappings,
  previousSteps,
  onUpdate,
  onRemove,
  collapsedItems,
  onToggleCollapse,
  className = '',
  showTransform = true
}: BaseMappingListProps) {
  return (
    <div className={`space-y-3${className}`}>
      {Object.entries(mappings).map(([key, mapping]) => (
        <BaseMappingItem
          key={key}
          mappingKey={key}
          mapping={mapping}
          isCollapsed={collapsedItems.includes(key)}
          previousSteps={previousSteps}
          onUpdate={onUpdate}
          onRemove={onRemove}
          onToggleCollapse={onToggleCollapse}
          showTransform={showTransform}
        />
      ))}
    </div>
  );
}