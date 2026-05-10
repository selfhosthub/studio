// ui/widgets/instance-view/InstanceSimpleView/components/ResourceGrid.tsx

"use client";

import {
  DndContext,
  closestCenter,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
} from "@dnd-kit/sortable";
import React, { useCallback, useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import { OrgFile } from "@/shared/types/api";
import { SortableResourceCard } from "@/widgets/instance-view/SortableResourceCard";
import { ResourceGridProps } from "../types";

export function ResourceGrid({
  hasIterations,
  flattenIterations,
  stepResources,
  selectedStep,
  selectedStepExecution,
  localResourceOrder,
  isReordering,
  orgSettings,
  stepSelectedIds,
  showPartialPlaceholders,
  remainingCount,
  gridClass,
  sensors,
  toggleResourceSelection,
  handleDragEnd,
  handleStepDragEnd,
  setViewingResource,
  onDownloadResource,
  onDeleteResources,
}: ResourceGridProps) {
  // Stable callback refs - use primitive IDs as deps so callbacks don't recreate
  // when parent re-renders with new object references but same logical values
  const stepId = selectedStep?.step_id;
  const jobId = selectedStepExecution?.id;
  const orderedResourcesRef = useRef<OrgFile[]>([]);

  const handleDelete = useCallback((resourceId: string) => {
    if (stepId && jobId && onDeleteResources) {
      onDeleteResources(stepId, jobId, [resourceId]);
    }
  }, [stepId, jobId, onDeleteResources]);

  const handleView = useCallback((r: OrgFile) => {
    setViewingResource({ resource: r, allResources: orderedResourcesRef.current });
  }, [setViewingResource]);

  const handleSelect = useCallback((resourceId: string) => {
    if (stepId) {
      toggleResourceSelection(stepId, resourceId);
    }
  }, [stepId, toggleResourceSelection]);

  const useStepReorder = hasIterations && flattenIterations;
  const orderKey = useStepReorder ? `step:${selectedStepExecution?.instance_step_id}` : (selectedStepExecution?.id || "");
  const localOrder = localResourceOrder[orderKey];

  const orderedResources = localOrder
    ? [...stepResources].sort((a: OrgFile, b: OrgFile) => {
        const aIdx = localOrder.indexOf(a.id);
        const bIdx = localOrder.indexOf(b.id);
        return (aIdx === -1 ? Infinity : aIdx) - (bIdx === -1 ? Infinity : bIdx);
      })
    : [...stepResources].sort((a: OrgFile, b: OrgFile) => {
        const aIter = a.metadata?.iteration_index ?? -1;
        const bIter = b.metadata?.iteration_index ?? -1;
        if (aIter !== bIter) return aIter - bIter;
        return a.display_order - b.display_order;
      });
  const canReorder = selectedStep?.status === "completed" && (useStepReorder || !!selectedStepExecution?.id) && !isReordering;

  useEffect(() => { orderedResourcesRef.current = orderedResources; });

  if (!hasIterations || flattenIterations) {
    return (
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={(e: DragEndEvent) => {
          if (useStepReorder && selectedStepExecution?.instance_step_id) {
            handleStepDragEnd(e, selectedStepExecution.instance_step_id, orderedResources);
          } else if (selectedStepExecution?.id) {
            handleDragEnd(e, selectedStepExecution.id, orderedResources);
          }
        }}
      >
        <SortableContext
          items={orderedResources.map((r: OrgFile) => r.id)}
          strategy={rectSortingStrategy}
        >
          <div className={gridClass}>
            {orderedResources.map((resource: OrgFile) => (
              <SortableResourceCard
                key={resource.id}
                resource={resource}
                onDownload={onDownloadResource}
                onDelete={selectedStep && selectedStepExecution && onDeleteResources ? handleDelete : undefined}
                onView={handleView}
                size={orgSettings.resourceCardSize}
                showThumbnails={orgSettings.showThumbnails}
                selectable={selectedStep?.status === "completed" && resource.status === "available"}
                selected={stepSelectedIds.has(resource.id)}
                onSelect={handleSelect}
                isDragEnabled={canReorder && resource.status === "available"}
              />
            ))}
            {showPartialPlaceholders && Array.from({ length: remainingCount }).map((_, i) => (
              <div
                key={`pending-placeholder-${i}`}
                className="aspect-square bg-card rounded-lg border-2 border-dashed border-primary flex flex-col items-center justify-center"
              >
                <Loader2 className="w-8 h-8 text-muted animate-spin mb-2" />
                <span className="text-xs text-secondary">Generating...</span>
              </div>
            ))}
          </div>
        </SortableContext>
      </DndContext>
    );
  }

  // Grouped iteration view is now handled by UnifiedIterationBlock in StepPanel.
  // ResourceGrid only handles flat views.
  return null;
}
