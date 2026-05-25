// ui/features/step-config/PreviousStepOutputsPanel/components/TypeFilterButton.tsx

'use client';

import { FilterType, TYPE_FILTER_CONFIG } from '../utils/panelUtils';

/**
 * Type filter button component
 */
export function TypeFilterButton({
  type,
  isActive,
  onClick,
  count
}: {
  type: FilterType;
  isActive: boolean;
  onClick: () => void;
  count: number;
}) {
  const config = TYPE_FILTER_CONFIG[type];

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={count === 0}
      className={`
        inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-mono rounded
        transition-colors duration-150
        ${isActive ? `${config.activeBg} ${config.activeText}` : `${config.bg} ${config.text}`}
        ${count === 0 ? 'opacity-40 cursor-not-allowed' : 'hover:opacity-80 cursor-pointer'}
      `}
      title={`Filter by ${type}${count > 0 ? ` (${count})` : ' (none)'}`}
    >
      {config.label}
    </button>
  );
}
