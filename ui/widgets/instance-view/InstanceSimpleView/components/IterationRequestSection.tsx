// ui/widgets/instance-view/InstanceSimpleView/components/IterationRequestSection.tsx

'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, CheckCircle2 } from 'lucide-react';
import { sanitizeForDisplay } from '@/shared/lib/displaySanitizer';
import { TreeNode } from './JsonTreeView';
import { TIMEOUTS } from '@/shared/lib/constants';

interface IterationRequest {
  iteration_index: number;
  params?: Record<string, any>;
  [key: string]: any;
}

interface IterationRequestSectionProps {
  id: string;
  iterationRequests: IterationRequest[];
  viewMode?: 'tree' | 'raw';
}

/**
 * Collapsible section showing per-iteration request data
 * Each iteration has its own expandable subsection
 */
export function IterationRequestSection({
  id,
  iterationRequests,
  viewMode = 'raw',
}: IterationRequestSectionProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedIterations, setExpandedIterations] = useState<Set<number>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const toggleMainSection = () => setIsExpanded(!isExpanded);

  const toggleIteration = (index: number) => {
    setExpandedIterations(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const handleCopy = async (data: any, copyId: string) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopiedId(copyId);
      setTimeout(() => setCopiedId(null), TIMEOUTS.COPY_FEEDBACK);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  const handleCopyAll = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await handleCopy(iterationRequests, `${id}-all`);
  };

  // Sort by iteration_index
  const sortedRequests = [...iterationRequests].sort(
    (a, b) => (a.iteration_index ?? 0) - (b.iteration_index ?? 0)
  );

  return (
    <div className="border border-primary rounded-lg overflow-hidden">
      {/* Main header */}
      <div
        role="button"
        tabIndex={0}
        onClick={toggleMainSection}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleMainSection(); } }}
        className="w-full flex items-center justify-between px-3 py-2 bg-surface hover:bg-card transition-colors cursor-pointer"
      >
        <span className="text-sm font-medium text-secondary">
          Request Data ({iterationRequests.length} iterations)
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopyAll}
            className="p-1 hover:bg-input rounded"
            title="Copy all iterations"
          >
            {copiedId === `${id}-all` ? (
              <CheckCircle2 className="w-4 h-4 text-success" />
            ) : (
              <Copy className="w-4 h-4 text-muted" />
            )}
          </button>
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-muted" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted" />
          )}
        </div>
      </div>

      {/* Iteration subsections */}
      {isExpanded && (
        <div className="bg-card divide-y divide-gray-100">
          {sortedRequests.map((iterReq, idx) => {
            const iterIndex = iterReq.iteration_index ?? idx;
            const isIterExpanded = expandedIterations.has(iterIndex);
            const iterData = iterReq.params || iterReq;
            const copyId = `${id}-iter-${iterIndex}`;

            return (
              <div key={iterIndex}>
                {/* Iteration header */}
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleIteration(iterIndex)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleIteration(iterIndex); } }}
                  className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface transition-colors cursor-pointer"
                >
                  <span className="text-sm text-secondary">
                    Iteration {iterIndex + 1}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCopy(iterData, copyId);
                      }}
                      className="p-1 hover:bg-input rounded"
                      title="Copy iteration data"
                    >
                      {copiedId === copyId ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                      ) : (
                        <Copy className="w-3.5 h-3.5 text-muted" />
                      )}
                    </button>
                    {isIterExpanded ? (
                      <ChevronDown className="w-4 h-4 text-muted" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-muted" />
                    )}
                  </div>
                </div>

                {/* Iteration content */}
                {isIterExpanded && (
                  <div className="px-3 pb-3 bg-surface">
                    {viewMode === 'tree' ? (
                      <div className="overflow-auto max-h-48 p-2 bg-card rounded border border-primary">
                        <TreeNode
                          keyName={null}
                          value={sanitizeForDisplay(iterData)}
                          path={[]}
                          depth={0}
                          editable={false}
                          editedPaths={new Set()}
                          onEdit={() => {}}
                        />
                      </div>
                    ) : (
                      <pre className="text-xs overflow-auto max-h-48 text-primary p-2 bg-card rounded border border-primary">
                        {JSON.stringify(sanitizeForDisplay(iterData), null, 2)}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default IterationRequestSection;
