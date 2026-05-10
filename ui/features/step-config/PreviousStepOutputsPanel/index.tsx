// ui/features/step-config/PreviousStepOutputsPanel/index.tsx

'use client';

import React, { useState } from 'react';
import { Step } from '@/entities/workflow';
import { Link2Off, X } from 'lucide-react';
import { SchemaView } from './components/SchemaView';
import { JsonView } from './components/JsonView';
import { TypeFilterButton } from './components/TypeFilterButton';
import { useEnhancedStepOutputs } from './hooks/useEnhancedStepOutputs';
import { ViewMode, FilterType, TYPE_FILTER_CONFIG, InputMapping } from './utils/panelUtils';

interface PreviousStepOutputsPanelProps {
  previousSteps: Step[];
  onFieldSelect?: (field: string, stepId: string, stepName: string) => void;
  inputMappings?: Record<string, InputMapping>;
  /** Instance form fields available for mapping (workflow-level runtime inputs) */
  instanceFormFields?: Record<string, { description?: string; type?: string; _from_form?: boolean; _owning_step_ids?: string[]; _owning_step_name?: string }>;
  /** Current step ID (to exclude own fields) */
  currentStepId?: string;
}

export function PreviousStepOutputsPanel({
  previousSteps,
  onFieldSelect,
  inputMappings,
  instanceFormFields,
  currentStepId,
}: PreviousStepOutputsPanelProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('schema');
  const [typeFilter, setTypeFilter] = useState<FilterType | null>(null);
  const [showUnmappedOnly, setShowUnmappedOnly] = useState(false);

  const { enhancedSteps, typeCounts, unmappedCount, totalOutputs } = useEnhancedStepOutputs(
    previousSteps,
    inputMappings
  );

  const toggleTypeFilter = (type: FilterType) => {
    setTypeFilter(current => current === type ? null : type);
  };

  return (
    <div className="h-full flex flex-col bg-surface border-r border-primary">
      {/* Header */}
      <div className="flex-shrink-0 p-3 border-b border-primary bg-card">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h3 className="text-sm font-semibold text-primary">
              INPUT
            </h3>
            <p className="text-muted text-xs">
              {previousSteps.length} step{previousSteps.length !== 1 ? 's' : ''} · {totalOutputs} field{totalOutputs !== 1 ? 's' : ''}
            </p>
          </div>

          {/* View Toggle - Schema | JSON */}
          <div className="flex rounded-md overflow-hidden border border-primary">
            <button
              type="button"
              onClick={() => setViewMode('schema')}
              className={`px-2.5 py-1 text-xs font-medium ${
                viewMode === 'schema'
                  ? 'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900' // css-check-ignore
                  : 'bg-card text-secondary hover:bg-card'
              }`}
            >
              Schema
            </button>
            <button
              type="button"
              onClick={() => setViewMode('json')}
              className={`px-2.5 py-1 text-xs font-medium border-l border-secondary ${
                viewMode === 'json'
                  ? 'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900' // css-check-ignore
                  : 'bg-card text-secondary hover:bg-card'
              }`}
            >
              JSON
            </button>
          </div>
        </div>

        {/* Type Filter Row */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-secondary mr-1">Filter:</span>
          {(Object.keys(TYPE_FILTER_CONFIG) as FilterType[]).map(type => (
            <TypeFilterButton
              key={type}
              type={type}
              isActive={typeFilter === type}
              onClick={() => toggleTypeFilter(type)}
              count={typeCounts[type]}
            />
          ))}
          {/* Unmapped filter button */}
          {inputMappings && (
            <button
              type="button"
              onClick={() => setShowUnmappedOnly(!showUnmappedOnly)}
              disabled={unmappedCount === 0 && !showUnmappedOnly}
              className={`
                inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded
                transition-colors duration-150
                ${showUnmappedOnly
                  ? 'bg-danger text-white'
                  : 'bg-card text-secondary'
                }
                ${unmappedCount === 0 && !showUnmappedOnly ? 'opacity-40 cursor-not-allowed' : 'hover:opacity-80 cursor-pointer'}
              `}
              title={`Show unmapped outputs (${unmappedCount})`}
            >
              <Link2Off className="h-3 w-3" />
              <span>{unmappedCount}</span>
            </button>
          )}
          {(typeFilter || showUnmappedOnly) && (
            <button
              type="button"
              onClick={() => {
                setTypeFilter(null);
                setShowUnmappedOnly(false);
              }}
              className="ml-1 p-0.5 rounded text-muted hover:text-secondary hover:bg-input"
              title="Clear all filters"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3">
        {viewMode === 'schema' && (
          <SchemaView
            previousSteps={enhancedSteps}
            onFieldSelect={onFieldSelect}
            typeFilter={typeFilter}
            showUnmappedOnly={showUnmappedOnly}
            inputMappings={inputMappings}
            instanceFormFields={instanceFormFields}
            currentStepId={currentStepId}
          />
        )}
        {viewMode === 'json' && (
          <JsonView previousSteps={enhancedSteps} typeFilter={typeFilter} />
        )}
      </div>
    </div>
  );
}

export default PreviousStepOutputsPanel;
