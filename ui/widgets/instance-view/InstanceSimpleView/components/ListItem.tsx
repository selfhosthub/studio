// ui/widgets/instance-view/InstanceSimpleView/components/ListItem.tsx

'use client';

import React from 'react';
import { getStatusIcon } from './StatusIcon';
import { StepModeBadges } from './StepModeBadges';

interface ListItemProps {
  icon: React.ReactNode;
  label: string;
  badge?: string | number;
  selected: boolean;
  onClick: () => void;
  status?: string;
  triggerType?: string;
  executionMode?: string;
}

/**
 * Left panel navigation list item component
 */
export function ListItem({
  icon,
  label,
  badge,
  selected,
  onClick,
  status,
  triggerType,
  executionMode,
}: ListItemProps) {
  const isSkip = executionMode === 'skip';
  const isStop = executionMode === 'stop';

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors ${ // css-check-ignore -- mode/trigger visualization
        selected
          ? 'bg-info-subtle text-info'
          : isSkip || isStop
            ? 'hover:bg-card text-muted'
            : 'hover:bg-card text-secondary'
      }`}
    >
      <div className="flex-shrink-0">{icon}</div>
      <span className={`flex-1 truncate font-medium ${isSkip || isStop ? 'line-through' : ''}`}>{label}</span>
      <StepModeBadges triggerType={triggerType} executionMode={executionMode} />
      {badge !== undefined && (
        <span className={`text-xs px-2 py-0.5 rounded-full ${
          selected
            ? 'bg-info-subtle text-info'
            : 'bg-input text-secondary'
        }`}>
          {badge}
        </span>
      )}
      {status && (
        <div className="flex-shrink-0">
          {getStatusIcon(status)}
        </div>
      )}
    </button>
  );
}

export default ListItem;
