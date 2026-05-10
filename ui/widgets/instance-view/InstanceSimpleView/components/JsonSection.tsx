// ui/widgets/instance-view/InstanceSimpleView/components/JsonSection.tsx

'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, CheckCircle2 } from 'lucide-react';
import { sanitizeForDisplay } from '@/shared/lib/displaySanitizer';
import { TIMEOUTS } from '@/shared/lib/constants';

interface JsonSectionProps {
  id: string;
  title: string;
  data: any;
  fallbackText: string;
}

/**
 * Collapsible JSON section component with copy functionality
 */
export function JsonSection({
  id,
  title,
  data,
  fallbackText,
}: JsonSectionProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copiedJson, setCopiedJson] = useState<string | null>(null);

  const hasData = data && Object.keys(data).length > 0;

  const handleCopyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopiedJson(id);
      setTimeout(() => setCopiedJson(null), TIMEOUTS.COPY_FEEDBACK);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <div className="border border-primary rounded-lg overflow-hidden">
      <div
        role="button"
        tabIndex={0}
        onClick={toggleExpanded}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpanded(); } }}
        className="w-full flex items-center justify-between px-3 py-2 bg-surface hover:bg-card transition-colors cursor-pointer"
      >
        <span className="text-sm font-medium text-secondary">{title}</span>
        <div className="flex items-center gap-2">
          {hasData && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleCopyJson();
              }}
              className="p-1 hover:bg-input rounded"
              title="Copy JSON"
            >
              {copiedJson === id ? (
                <CheckCircle2 className="w-4 h-4 text-success" />
              ) : (
                <Copy className="w-4 h-4 text-muted" />
              )}
            </button>
          )}
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-muted" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted" />
          )}
        </div>
      </div>
      {isExpanded && (
        <div className="p-3 bg-card">
          {hasData ? (
            <pre className="text-xs overflow-auto max-h-60 text-primary">
              {JSON.stringify(sanitizeForDisplay(data), null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-muted dark:text-secondary italic">{fallbackText}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default JsonSection;
