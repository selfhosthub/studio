// ui/widgets/instance-view/InstanceSimpleView/components/StepFileToolbar.tsx

"use client";

import { useState, useEffect, useRef } from "react";
import {
  Loader2,
  Download,
  RotateCw,
  Trash2,
  Grid3X3,
  LayoutGrid,
  Square,
  Layers,
  List,
  Upload,
  Folder,
  ChevronDown,
} from "lucide-react";
import { OrgFile } from "@/shared/types/api";
import { addFilesFromLibraryToStep } from "@/shared/api";
import { FileLibraryModal } from "@/features/files";

import { StepFileToolbarProps } from "../types";

export function StepFileToolbar({
  selectedStep,
  selectedStepExecution,
  instance,
  stepResources,
  stepSelectedIds,
  stepSelectedCount,
  fileCountDisplay,
  isDownloading,
  regeneratingResources,
  deletingResources,
  flattenIterations,
  setFlattenIterations,
  orgSettings,
  updateSettings,
  onRegenerateResources,
  onDeleteResources,
  handleDownloadFiles,
  clearSelection,
  onUploadFilesToStep,
}: StepFileToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [showAddFilesDropdown, setShowAddFilesDropdown] = useState(false);
  const [showLibraryModal, setShowLibraryModal] = useState(false);
  const [isAddingFromLibrary, setIsAddingFromLibrary] = useState(false);
  const addFilesDropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (addFilesDropdownRef.current && !addFilesDropdownRef.current.contains(event.target as Node)) {
        setShowAddFilesDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Handler for adding files from library
  const handleAddFromLibrary = async (resourceIds: string[]) => {
    if (!instance?.id || !selectedStep?.step_id) return;
    setIsAddingFromLibrary(true);
    try {
      await addFilesFromLibraryToStep(instance.id, selectedStep.step_id, resourceIds);
      // Temporary: force refresh to show new files
      window.location.reload();
    } catch (err) {
      console.error("Failed to add files from library:", err);
    } finally {
      setIsAddingFromLibrary(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
      <h4 className="text-sm font-medium text-secondary">
        Files {fileCountDisplay}
        {stepSelectedCount > 0 && (
          <span className="ml-2 text-info">
            ({stepSelectedCount} selected)
          </span>
        )}
      </h4>
      <div className="flex items-center gap-2">
        {stepSelectedCount > 0 && selectedStep && selectedStepExecution && (
          <>
            <button
              onClick={() => {
                onRegenerateResources(
                  selectedStep.step_id,
                  selectedStepExecution.id,
                  Array.from(stepSelectedIds)
                );
                clearSelection(selectedStep.step_id);
              }}
              disabled={regeneratingResources}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-info-subtle text-info rounded hover:bg-[var(--theme-primary)]/20 disabled:opacity-50 transition-colors"
            >
              <RotateCw className={`w-3 h-3 ${regeneratingResources ? "animate-spin" : ""}`} />
              {regeneratingResources ? "Regenerating..." : `Regenerate (${stepSelectedCount})`}
            </button>
            <button
              onClick={() => {
                onDeleteResources(
                  selectedStep.step_id,
                  selectedStepExecution.id,
                  Array.from(stepSelectedIds)
                );
                clearSelection(selectedStep.step_id);
              }}
              disabled={deletingResources}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-danger-subtle text-danger rounded hover:bg-[var(--theme-danger)]/20 disabled:opacity-50 transition-colors"
            >
              <Trash2 className="w-3 h-3" />
              {deletingResources ? "Deleting..." : `Delete (${stepSelectedCount})`}
            </button>
          </>
        )}
        {stepResources.length > 0 && (
          <button
            onClick={() => {
              const toDownload = stepSelectedCount > 0
                ? stepResources.filter((r: OrgFile) => stepSelectedIds.has(r.id))
                : stepResources;
              handleDownloadFiles(toDownload);
            }}
            disabled={isDownloading}
            className="flex items-center gap-1.5 px-2 py-1 text-xs bg-card text-secondary rounded hover:bg-input disabled:opacity-50"
          >
            {isDownloading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5" />
            )}
            {isDownloading
              ? "Creating zip..."
              : stepSelectedCount > 0
                ? `Download Selected (${stepSelectedCount})`
                : "Download All"}
          </button>
        )}
        {/* Add Files Button with Dropdown */}
        {selectedStep?.status === "completed" && (
          <div ref={addFilesDropdownRef} className="relative">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,video/*,audio/*"
              className="hidden"
              onChange={async (e) => {
                const files = Array.from(e.target.files || []);
                if (files.length === 0) return;
                setIsUploading(true);
                try {
                  if (onUploadFilesToStep && selectedStepExecution) {
                    await onUploadFilesToStep(selectedStep.step_id, selectedStepExecution.id, files);
                  }
                } finally {
                  setIsUploading(false);
                  if (fileInputRef.current) {
                    fileInputRef.current.value = "";
                  }
                }
              }}
            />
            <button
              onClick={() => setShowAddFilesDropdown(!showAddFilesDropdown)}
              disabled={isUploading || isAddingFromLibrary}
              className="flex items-center gap-1.5 px-2 py-1 text-xs bg-success-subtle text-success rounded hover:bg-[var(--theme-success)]/20 disabled:opacity-50"
            >
              {isUploading || isAddingFromLibrary ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5" />
              )}
              {isUploading ? "Uploading..." : isAddingFromLibrary ? "Adding..." : "Add Files"}
              <ChevronDown className="w-3 h-3" />
            </button>
            {/* Dropdown Menu */}
            {showAddFilesDropdown && (
              <div className="absolute right-0 mt-1 w-48 bg-card border border-primary rounded-lg shadow-lg z-10">
                <button
                  onClick={() => {
                    setShowAddFilesDropdown(false);
                    fileInputRef.current?.click();
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-card rounded-t-lg"
                >
                  <Upload className="w-4 h-4" />
                  Upload from Computer
                </button>
                <button
                  onClick={() => {
                    setShowAddFilesDropdown(false);
                    setShowLibraryModal(true);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-card rounded-b-lg"
                >
                  <Folder className="w-4 h-4" />
                  Browse Library
                </button>
              </div>
            )}
            {/* Library Modal */}
            <FileLibraryModal
              isOpen={showLibraryModal}
              onClose={() => setShowLibraryModal(false)}
              onSelect={handleAddFromLibrary}
              mediaTypeFilter="image"
              title="Add Files from Library"
            />
          </div>
        )}
        {stepResources.some((r: OrgFile) => r.metadata?.iteration_index !== undefined) && (
          <button
            onClick={() => setFlattenIterations(!flattenIterations)}
            className={`p-1.5 border rounded ${
              flattenIterations
                ? "bg-info-subtle text-info border-info"
                : "text-muted hover:bg-surface border-primary"
            }`}
            title={flattenIterations ? "Group by iteration" : "Flatten for reordering"}
          >
            {flattenIterations ? <Layers className="w-3.5 h-3.5" /> : <List className="w-3.5 h-3.5" />}
          </button>
        )}
        <div className="flex items-center border border-primary rounded overflow-hidden">
          <button
            onClick={() => updateSettings({ resourceCardSize: "small" })}
            className={`p-1.5${orgSettings.resourceCardSize === "small" ? " bg-info-subtle text-info" : " text-muted hover:bg-surface"}`}
            title="Small thumbnails"
          >
            <Grid3X3 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => updateSettings({ resourceCardSize: "medium" })}
            className={`p-1.5 border-x border-primary${orgSettings.resourceCardSize === "medium" ? " bg-info-subtle text-info" : " text-muted hover:bg-surface"}`}
            title="Medium thumbnails"
          >
            <LayoutGrid className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => updateSettings({ resourceCardSize: "large" })}
            className={`p-1.5${orgSettings.resourceCardSize === "large" ? " bg-info-subtle text-info" : " text-muted hover:bg-surface"}`}
            title="Large thumbnails"
          >
            <Square className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
