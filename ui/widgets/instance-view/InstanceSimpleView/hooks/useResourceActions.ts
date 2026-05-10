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
  };
}
