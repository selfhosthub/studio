// ui/shared/ui/JsonOutputView.tsx

'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';
import { TIMEOUTS } from '@/shared/lib/constants';

interface JsonOutputViewProps {
  id: string;
  title: string;
  data: any;
  className?: string;
}

/**
 * Renders JSON data in a collapsible section with copy functionality.
 * Used as the default/fallback output view.
 */
export function JsonOutputView({
  id,
  title,
  data,
  className = '',
}: JsonOutputViewProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [copied, setCopied] = useState(false);

  const jsonString = data ? JSON.stringify(data, null, 2) : '';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(jsonString);
      setCopied(true);
      setTimeout(() => setCopied(false), TIMEOUTS.COPY_FEEDBACK);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  if (!data) {
    return (
      <div className={`text-sm text-secondary italic ${className}`}>
        No data available
      </div>
    );
  }

  return (
    <div className={`border border-primary rounded-lg overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between bg-surface">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex-1 flex items-center gap-2 px-3 py-2 hover:bg-card transition-colors"
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-secondary" />
          ) : (
            <ChevronRight className="w-4 h-4 text-secondary" />
          )}
          <span className="text-sm font-medium text-secondary">
            {title}
          </span>
        </button>
        <button
          onClick={handleCopy}
          className="px-3 py-2 hover:bg-card transition-colors border-l border-primary"
          title="Copy JSON"
        >
          {copied ? (
            <Check className="w-4 h-4 text-success" />
          ) : (
            <Copy className="w-4 h-4 text-muted" />
          )}
        </button>
      </div>

      {/* JSON Content */}
      {isExpanded && (
        <pre className="p-3 text-xs font-mono text-primary bg-surface overflow-x-auto max-h-96">
          {jsonString}
        </pre>
      )}
    </div>
  );
}
