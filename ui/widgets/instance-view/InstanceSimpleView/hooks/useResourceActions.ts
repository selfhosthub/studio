// ui/widgets/instance-view/InstanceSimpleView/hooks/useResourceActions.ts

import { useState, useCallback } from "react";
import { DragEndEvent } from "@dnd-kit/core";
import { arrayMove } from "@dnd-kit/sortable";
import { OrgFile } from "@/shared/types/api";
import { downloadResource, reorderJobFiles, reorderStepFiles } from "@/shared/api";
import { getFilename } from "../utils";

interface UseResourceActionsOptions {
  onDownloadResource: (resourceId: string, filename: string) => void;
}

interface UseResourceActionsReturn {
  /** Optimistic local ordering keyed by jobId or "step:{stepId}" */
  localResourceOrder: Record<string, string[]>;
  /** Whether a reorder request is in flight */
  isReordering: boolean;
  /** Whether a zip download is in progress */
  isDownloading: boolean;
  /** Selected resource IDs keyed by stepId */
  selectedResourceIds: Record<string, Set<string>>;
  /** Toggle a single resource selection within a step */
  toggleResourceSelection: (stepId: string, resourceId: string) => void;
  /** Get selected count for a step */
  getSelectedCount: (stepId: string) => number;
  /** Clear all selections for a step */
  clearSelection: (stepId: string) => void;
  /** Download one file directly or multiple as a zip */
  handleDownloadFiles: (resources: OrgFile[]) => Promise<void>;
  /** Handle drag-end for job-scoped reordering */
  handleDragEnd: (event: DragEndEvent, jobId: string, resources: OrgFile[]) => Promise<void>;
  /** Handle drag-end for step-scoped reordering */
  handleStepDragEnd: (event: DragEndEvent, stepId: string, resources: OrgFile[]) => Promise<void>;
  /** Stage a step-scoped reorder locally (does NOT persist; flush via flushStepReorder before run) */
  stageStepReorder: (stepId: string, orderedIds: string[]) => void;
  /** Persist any locally-staged reorder for this step to the DB. Returns true if a flush happened. */
  flushStepReorder: (stepId: string) => Promise<boolean>;
  /** Drop any locally-staged reorder for a step (e.g. on regen / delete invalidating IDs) */
  discardStepReorder: (stepId: string) => void;
  /** True if a step has a locally-staged reorder waiting to flush */
  hasPendingReorder: (stepId: string) => boolean;
}

/**
 * Encapsulates resource selection state, download (single + zip),
 * and drag-and-drop reorder logic for both job-scoped and step-scoped ordering.
 */
export function useResourceActions({
  onDownloadResource,
}: UseResourceActionsOptions): UseResourceActionsReturn {
  const [localResourceOrder, setLocalResourceOrder] = useState<Record<string, string[]>>({});
  const [isReordering, setIsReordering] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [selectedResourceIds, setSelectedResourceIds] = useState<Record<string, Set<string>>>({});

  const toggleResourceSelection = useCallback((stepId: string, resourceId: string) => {
    setSelectedResourceIds((prev) => {
      const stepSet = prev[stepId] || new Set();
      const newSet = new Set(stepSet);
      if (newSet.has(resourceId)) {
        newSet.delete(resourceId);
      } else {
        newSet.add(resourceId);
      }
      return { ...prev, [stepId]: newSet };
    });
  }, []);

  const getSelectedCount = useCallback(
    (stepId: string) => selectedResourceIds[stepId]?.size || 0,
    [selectedResourceIds]
  );

  const clearSelection = useCallback((stepId: string) => {
    setSelectedResourceIds((prev) => {
      const newState = { ...prev };
      delete newState[stepId];
      return newState;
    });
  }, []);

  const handleDownloadFiles = useCallback(
    async (resources: OrgFile[]) => {
      if (resources.length === 0) return;

      if (resources.length === 1) {
        const r = resources[0];
        const filename = getFilename(r);
        onDownloadResource(r.id, filename);
        return;
      }

      setIsDownloading(true);
      try {
        const { default: JSZip } = await import("jszip");
        const zip = new JSZip();
        const filePromises = resources.map(async (r) => {
          const blob = await downloadResource(r.id);
          const filename = getFilename(r);
          return { filename, blob };
        });

        const files = await Promise.all(filePromises);
        for (const { filename, blob } of files) {
          zip.file(filename, blob);
        }

        const zipBlob = await zip.generateAsync({ type: "blob" });
        const url = URL.createObjectURL(zipBlob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `files_${new Date().toISOString().slice(0, 10)}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } catch (error) {
        console.error("Failed to create zip:", error);
      } finally {
        setIsDownloading(false);
      }
    },
    [onDownloadResource]
  );

  const handleDragEnd = useCallback(
    async (event: DragEndEvent, jobId: string, resources: OrgFile[]) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;

      const oldIndex = resources.findIndex((r) => r.id === active.id);
      const newIndex = resources.findIndex((r) => r.id === over.id);

      if (oldIndex === -1 || newIndex === -1) return;

      const newOrder = arrayMove(resources, oldIndex, newIndex);
      setLocalResourceOrder((prev) => ({
        ...prev,
        [jobId]: newOrder.map((r) => r.id),
      }));

      setIsReordering(true);
      try {
        await reorderJobFiles(jobId, newOrder.map((r) => r.id));
      } catch (error) {
        console.error("Failed to reorder resources:", error);
        setLocalResourceOrder((prev) => {
          const { [jobId]: _, ...rest } = prev;
          return rest;
        });
      } finally {
        setIsReordering(false);
      }
    },
    []
  );

  const handleStepDragEnd = useCallback(
    async (event: DragEndEvent, stepId: string, resources: OrgFile[]) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;

      const oldIndex = resources.findIndex((r) => r.id === active.id);
      const newIndex = resources.findIndex((r) => r.id === over.id);

      if (oldIndex === -1 || newIndex === -1) return;

      const newOrder = arrayMove(resources, oldIndex, newIndex);
      const orderKey = `step:${stepId}`;
      setLocalResourceOrder((prev) => ({
        ...prev,
        [orderKey]: newOrder.map((r) => r.id),
      }));

      setIsReordering(true);
      try {
        await reorderStepFiles(stepId, newOrder.map((r) => r.id));
      } catch (error) {
        console.error("Failed to reorder step resources:", error);
        setLocalResourceOrder((prev) => {
          const { [orderKey]: _, ...rest } = prev;
          return rest;
        });
      } finally {
        setIsReordering(false);
      }
    },
    []
  );

  // Local-only stage: writes the new order to localResourceOrder so the
  // optimistic UI updates immediately. Does NOT call the API.
  // Persistence happens on Run/Rerun via flushStepReorder.
  const stageStepReorder = useCallback((stepId: string, orderedIds: string[]) => {
    const orderKey = `step:${stepId}`;
    setLocalResourceOrder((prev) => ({ ...prev, [orderKey]: orderedIds }));
  }, []);

  // Flushes any staged reorder for the step to the DB. Returns true if a
  // flush happened, false if nothing was staged. Throws on API error so the
  // caller can decide whether to proceed with run.
  const flushStepReorder = useCallback(async (stepId: string): Promise<boolean> => {
    const orderKey = `step:${stepId}`;
    const orderedIds = localResourceOrder[orderKey];
    if (!orderedIds || orderedIds.length === 0) return false;
    setIsReordering(true);
    try {
      await reorderStepFiles(stepId, orderedIds);
      setLocalResourceOrder((prev) => {
        const { [orderKey]: _, ...rest } = prev;
        return rest;
      });
      return true;
    } finally {
      setIsReordering(false);
    }
  }, [localResourceOrder]);

  const discardStepReorder = useCallback((stepId: string) => {
    const orderKey = `step:${stepId}`;
    setLocalResourceOrder((prev) => {
      const { [orderKey]: _, ...rest } = prev;
      return rest;
    });
  }, []);

  const hasPendingReorder = useCallback((stepId: string): boolean => {
    return !!localResourceOrder[`step:${stepId}`]?.length;
  }, [localResourceOrder]);

  return {
    localResourceOrder,
    isReordering,
    isDownloading,
    selectedResourceIds,
    toggleResourceSelection,
    getSelectedCount,
    clearSelection,
    handleDownloadFiles,
    handleDragEnd,
    handleStepDragEnd,
    stageStepReorder,
    flushStepReorder,
    discardStepReorder,
    hasPendingReorder,
  };
}
