// ui/widgets/instance-view/InstanceSimpleView/components/UnifiedIterationBlock.tsx

'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  XCircle,
  Layers,
  FileText,
  Copy,
  CheckCircle2,
} from 'lucide-react';
import { OrgFile } from '@/shared/types/api';
import { sanitizeForDisplay } from '@/shared/lib/displaySanitizer';
import { TreeNode } from './JsonTreeView';
import { SortableResourceCard } from '@/widgets/instance-view/SortableResourceCard';

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
  gridClass: string;
  orgSettings: { resourceCardSize: 'small' | 'medium' | 'large'; showThumbnails: boolean };
  onViewResource: (resource: OrgFile, allResources: OrgFile[]) => void;
  onDownloadResource: (resourceId: string, filename: string) => void;
  isDragEnabled: boolean;
  regenerating: boolean;
  deleting: boolean;
  stepStatus: string;
  viewMode?: 'tree' | 'raw';
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
  gridClass,
  orgSettings,
  onViewResource,
  onDownloadResource,
  isDragEnabled,
  regenerating,
  deleting,
  stepStatus,
  viewMode = 'tree',
}: UnifiedIterationBlockProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [showParams, setShowParams] = useState(false);
  const [localViewMode, setLocalViewMode] = useState<'tree' | 'raw'>(viewMode);
  const [copied, setCopied] = useState(false);

  // Stable callbacks - one ref per render instead of N inline arrows per map iteration
  const resourcesRef = useRef<OrgFile[]>(resources);
  useEffect(() => { resourcesRef.current = resources; });

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
        {isFailed && canAct && (
          <div className="flex items-center gap-1 text-xs text-danger">
            Failed
          </div>
        )}
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
                        setTimeout(() => setCopied(false), 1500);
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
          {(resources.length > 0 || placeholderCount > 0) && (
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
          )}

          {/* Empty state for failed/empty iterations */}
          {resources.length === 0 && !isGenerating && (
            <div className="flex items-center justify-center py-6 text-sm text-secondary border-2 border-dashed border-primary rounded-lg">
              {isFailed ? 'No files - worker failed or crashed' : 'No files yet'}
            </div>
          )}

        </div>
      )}
    </div>
  );
}
