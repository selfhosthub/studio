// ui/widgets/instance-view/InstanceSimpleView/components/UnifiedIterationBlock.tsx

'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { TIMEOUTS } from '@/shared/lib/constants';
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  XCircle,
  Layers,
  FileText,
  Copy,
  CheckCircle2,
  RotateCw,
} from 'lucide-react';
import {
  DndContext,
  DragEndEvent,
  SensorDescriptor,
  SensorOptions,
  closestCenter,
} from '@dnd-kit/core';
import { SortableContext, arrayMove, rectSortingStrategy } from '@dnd-kit/sortable';
import { OrgFile } from '@/shared/types/api';
import { sanitizeForDisplay } from '@/shared/lib/displaySanitizer';
import { TreeNode } from './JsonTreeView';
import { SortableResourceCard } from '@/widgets/instance-view/SortableResourceCard';
import ResourceCard from '@/widgets/instance-view/ResourceCard';

interface UnifiedIterationBlockProps {
  iterationIndex: number;
  resources: OrgFile[];
  expectedCount: number;
  isComplete: boolean;
  requestParams: Record<string, unknown> | null;
  isGenerating: boolean;
  isFailed: boolean;
  selectedIds: Set<string>;
  onToggleSelect: (resourceId: string) => void;
  onRegenerateIteration: (iterationIndex: number) => void;
  onRegenerateSelected: (resourceIds: string[]) => void;
  onDeleteSelected: (resourceIds: string[]) => void;
  onSelectVariant: (resourceId: string) => void;
  gridClass: string;
  orgSettings: { resourceCardSize: 'small' | 'medium' | 'large'; showThumbnails: boolean };
  onViewResource: (resource: OrgFile, allResources: OrgFile[]) => void;
  onDownloadResource: (resourceId: string, filename: string) => void;
  isDragEnabled: boolean;
  regenerating: boolean;
  deleting: boolean;
  stepStatus: string;
  viewMode?: 'tree' | 'raw';
  /** dnd-kit sensors (provided when reorder is enabled) */
  sensors?: SensorDescriptor<SensorOptions>[];
  /** Called with the new ordered resource IDs for this iteration after a drag */
  onReorderWithinIteration?: (newOrderedIds: string[]) => void;
}

export function UnifiedIterationBlock({
  iterationIndex,
  resources,
  expectedCount,
  isComplete,
  requestParams,
  isGenerating,
  isFailed,
  selectedIds,
  onToggleSelect,
  onRegenerateIteration,
  onRegenerateSelected,
  onDeleteSelected,
  onSelectVariant,
  gridClass,
  orgSettings,
  onViewResource,
  onDownloadResource,
  isDragEnabled,
  regenerating,
  deleting,
  stepStatus,
  viewMode = 'tree',
  sensors,
  onReorderWithinIteration,
}: UnifiedIterationBlockProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [showParams, setShowParams] = useState(false);
  const [showVariants, setShowVariants] = useState(false);
  const [localViewMode, setLocalViewMode] = useState<'tree' | 'raw'>(viewMode);
  const [copied, setCopied] = useState(false);

  // Stable callbacks - one ref per render instead of N inline arrows per map iteration
  const resourcesRef = useRef<OrgFile[]>(resources);
  useEffect(() => { resourcesRef.current = resources; });

  // Auto-expand the variant strip when a new variant lands at runtime (i.e. a
  // regeneration the user just triggered), so the happy path is regen -> see
  // both -> pick one, not discovery-dependent. Resets to collapsed on remount.
  // Adjusted during render (not in an effect) so the change lands before commit.
  const [prevVariantCount, setPrevVariantCount] = useState(resources.length);
  if (resources.length !== prevVariantCount) {
    if (resources.length > prevVariantCount && resources.length > 1) {
      setShowVariants(true);
    }
    // Collapse back to the single card (which carries the regenerate action) once
    // a slot drops to one variant — e.g. after deleting all but one candidate.
    if (resources.length <= 1) {
      setShowVariants(false);
    }
    setPrevVariantCount(resources.length);
  }

  const handleRegenerate = useCallback((resourceId: string) => {
    onRegenerateSelected([resourceId]);
  }, [onRegenerateSelected]);

  const handleDelete = useCallback((resourceId: string) => {
    onDeleteSelected([resourceId]);
  }, [onDeleteSelected]);

  const handleView = useCallback((r: OrgFile) => {
    onViewResource(r, resourcesRef.current);
  }, [onViewResource]);

  const placeholderCount = !isComplete && isGenerating
    ? Math.max(0, expectedCount - resources.length)
    : 0;
  const canAct = stepStatus === 'completed' || stepStatus === 'failed';

  // Keep-variants: when the backend flags a selected variant, collapse the slot
  // to the chosen image and let the user expand a strip to pick a different one.
  const keepVariants = resources.some(r => r.is_selected);
  const activeVariant = resources.find(r => r.is_selected) ?? resources[0];
  const hasMultipleVariants = resources.length > 1;

  // Scale the variant-comparison strip to the user's chosen card size so an
  // auto-expanded strip after regen doesn't shrink the slot below their setting.
  const variantStripWidth = orgSettings.resourceCardSize === 'small'
    ? 'w-36'
    : orgSettings.resourceCardSize === 'large'
      ? 'w-64'
      : 'w-44';

  const fileLabel = isComplete
    ? `${resources.length} ${resources.length === 1 ? 'file' : 'files'}`
    : `${resources.length}/${expectedCount} files`;

  return (
    <div className="border border-primary rounded-lg overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-surface cursor-pointer select-none"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-secondary" />
          ) : (
            <ChevronRight className="w-4 h-4 text-secondary" />
          )}
          <span className="text-sm font-medium text-secondary">
            Iteration {iterationIndex + 1}
          </span>
          <span className="text-xs text-secondary">
            ({fileLabel})
          </span>
          {isFailed && (
            <XCircle className="w-4 h-4 text-danger" />
          )}
          {isGenerating && !isComplete && (
            <Loader2 className="w-3.5 h-3.5 text-info animate-spin" />
          )}
        </div>
        <div className="flex items-center gap-2">
          {isFailed && canAct && (
            <span className="text-xs text-danger">Failed</span>
          )}
          {canAct && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRegenerateIteration(iterationIndex);
              }}
              className="flex items-center gap-1 px-2 py-1 text-xs text-secondary hover:text-primary rounded hover:bg-primary/10"
              title="Regenerate this scene from its prompt"
            >
              <RotateCw className="w-3.5 h-3.5" />
              Regenerate
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      {isExpanded && (
        <div className="p-3 space-y-3">
          {/* Request params */}
          {requestParams && (
            <div>
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setShowParams(!showParams)}
                  className="flex items-center gap-1 text-xs text-secondary hover:text-secondary"
                >
                  {showParams ? (
                    <ChevronDown className="w-3 h-3" />
                  ) : (
                    <ChevronRight className="w-3 h-3" />
                  )}
                  Request Parameters
                </button>
                {showParams && (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setLocalViewMode('tree')}
                      className={`px-1.5 py-0.5 text-[10px] rounded ${localViewMode === 'tree' ? 'bg-info text-white' : 'bg-surface text-secondary hover:bg-input'}`}
                    >
                      <Layers className="w-2.5 h-2.5 inline mr-0.5" />Tree
                    </button>
                    <button
                      onClick={() => setLocalViewMode('raw')}
                      className={`px-1.5 py-0.5 text-[10px] rounded ${localViewMode === 'raw' ? 'bg-info text-white' : 'bg-surface text-secondary hover:bg-input'}`}
                    >
                      <FileText className="w-2.5 h-2.5 inline mr-0.5" />JSON
                    </button>
                    <button
                      onClick={async () => {
                        await navigator.clipboard.writeText(JSON.stringify(requestParams, null, 2));
                        setCopied(true);
                        setTimeout(() => setCopied(false), TIMEOUTS.COPY_FEEDBACK_SHORT);
                      }}
                      className="p-0.5 hover:bg-input rounded"
                      title="Copy request parameters"
                    >
                      {copied ? <CheckCircle2 className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3 text-muted" />}
                    </button>
                  </div>
                )}
              </div>
              {showParams && (
                <div className="mt-1 overflow-auto max-h-48 p-2 bg-card rounded border border-primary text-xs">
                  {localViewMode === 'tree' ? (
                    <TreeNode
                      keyName={null}
                      value={sanitizeForDisplay(requestParams)}
                      path={[]}
                      depth={0}
                      editable={false}
                      editedPaths={new Set()}
                      onEdit={() => {}}
                    />
                  ) : (
                    <pre className="text-primary">
                      {JSON.stringify(sanitizeForDisplay(requestParams), null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Resource grid */}
          {(resources.length > 0 || placeholderCount > 0) && (() => {
            // Keep-variants: show the selected image by default; expand a strip
            // to compare and pick a different variant for this slot.
            if (keepVariants) {
              return (
                <div className="space-y-2">
                  {showVariants ? (
                    <div className="flex gap-3 overflow-x-auto pb-1">
                      {resources.map(resource => (
                        <div key={resource.id} className={`${variantStripWidth} flex-shrink-0`}>
                          <ResourceCard
                            resource={resource}
                            onDownload={onDownloadResource}
                            onView={handleView}
                            onDelete={canAct ? handleDelete : undefined}
                            onUseVariant={canAct ? onSelectVariant : undefined}
                            variantActive={resource.is_selected}
                            size={orgSettings.resourceCardSize}
                            showThumbnails={orgSettings.showThumbnails}
                          />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className={gridClass}>
                      {activeVariant && (
                        <ResourceCard
                          resource={activeVariant}
                          onDownload={onDownloadResource}
                          onRegenerate={canAct ? handleRegenerate : undefined}
                          onDelete={canAct ? handleDelete : undefined}
                          onView={handleView}
                          size={orgSettings.resourceCardSize}
                          showThumbnails={orgSettings.showThumbnails}
                          selectable={canAct && activeVariant.status === 'available'}
                          selected={selectedIds.has(activeVariant.id)}
                          onSelect={onToggleSelect}
                        />
                      )}
                    </div>
                  )}
                  {hasMultipleVariants && (
                    <button
                      onClick={() => setShowVariants(v => !v)}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-info-subtle text-info hover:bg-info-subtle/70"
                      title="Compare variants for this scene"
                    >
                      <Layers className="w-3.5 h-3.5" />
                      {resources.length} variants
                      {showVariants ? (
                        <ChevronDown className="w-3 h-3" />
                      ) : (
                        <ChevronRight className="w-3 h-3" />
                      )}
                    </button>
                  )}
                </div>
              );
            }
            const grid = (
              <div className={gridClass}>
                {resources.map(resource => (
                  <SortableResourceCard
                    key={resource.id}
                    resource={resource}
                    onDownload={onDownloadResource}
                    onRegenerate={canAct ? handleRegenerate : undefined}
                    onDelete={canAct ? handleDelete : undefined}
                    onView={handleView}
                    size={orgSettings.resourceCardSize}
                    showThumbnails={orgSettings.showThumbnails}
                    selectable={canAct && resource.status === 'available'}
                    selected={selectedIds.has(resource.id)}
                    onSelect={onToggleSelect}
                    isDragEnabled={isDragEnabled && resource.status === 'available'}
                  />
                ))}
                {placeholderCount > 0 && Array.from({ length: placeholderCount }).map((_, i) => (
                  <div
                    key={`placeholder-${iterationIndex}-${i}`}
                    className="aspect-square bg-card rounded-lg border-2 border-dashed border-primary flex flex-col items-center justify-center"
                  >
                    <Loader2 className="w-8 h-8 text-muted animate-spin mb-2" />
                    <span className="text-xs text-secondary">Generating...</span>
                  </div>
                ))}
              </div>
            );
            // When reorder is enabled, scope drag to this iteration's resources
            // so drops can't cross iteration boundaries and the parent gets
            // back a clean ordered list to persist.
            if (isDragEnabled && sensors && onReorderWithinIteration && resources.length > 1) {
              const handleDragEnd = (e: DragEndEvent) => {
                const { active, over } = e;
                if (!over || active.id === over.id) return;
                const oldIndex = resources.findIndex((r) => r.id === active.id);
                const newIndex = resources.findIndex((r) => r.id === over.id);
                if (oldIndex === -1 || newIndex === -1) return;
                const newOrder = arrayMove(resources, oldIndex, newIndex);
                onReorderWithinIteration(newOrder.map((r) => r.id));
              };
              return (
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                  <SortableContext items={resources.map((r) => r.id)} strategy={rectSortingStrategy}>
                    {grid}
                  </SortableContext>
                </DndContext>
              );
            }
            return grid;
          })()}

          {/* Empty state for failed/empty iterations */}
          {resources.length === 0 && !isGenerating && (
            <div className="flex items-center justify-center py-6 text-sm text-secondary border-2 border-dashed border-primary rounded-lg">
              {isFailed ? 'No image generated - this scene failed' : 'No files yet'}
            </div>
          )}

        </div>
      )}
    </div>
  );
}
