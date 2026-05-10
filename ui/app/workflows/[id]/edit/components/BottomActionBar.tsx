// ui/app/workflows/[id]/edit/components/BottomActionBar.tsx

'use client';

import { Save, Play, Copy, Download } from 'lucide-react';
import Link from 'next/link';

interface BottomActionBarProps {
  hasUnsavedChanges: boolean;
  isSubmitting: boolean;
  isRunning: boolean;
  isExporting: boolean;
  hasSteps: boolean;
  onRun: () => void;
  onSaveAs: () => void;
  onExport: () => void;
}

export function BottomActionBar({
  hasUnsavedChanges,
  isSubmitting,
  isRunning,
  isExporting,
  hasSteps,
  onRun,
  onSaveAs,
  onExport,
}: BottomActionBarProps) {
  return (
    <div className="mt-6 flex justify-end space-x-4">
      <Link
        href="/workflows/list"
        className="btn-orange text-sm inline-flex items-center"
      >
        Cancel
      </Link>
      <button
        type="submit"
        className={`${hasUnsavedChanges ? 'btn-orange' : 'btn-success'} text-sm inline-flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
        disabled={isSubmitting}
      >
        {isSubmitting ? (
          <>
            <span className="spinner-sm" />
            Saving...
          </>
        ) : (
          <>
            <Save className="h-4 w-4" />
            Save
          </>
        )}
      </button>
      <button
        type="button"
        onClick={onRun}
        disabled={isRunning || !hasSteps}
        className="btn-primary text-sm inline-flex items-center"
      >
        <Play className="h-4 w-4 mr-2" />
        {isRunning ? 'Running...' : 'Run'}
      </button>
      <button
        type="button"
        onClick={onSaveAs}
        className="btn-success text-sm inline-flex items-center"
      >
        <Copy className="h-4 w-4 mr-2" />
        Save As...
      </button>
      <button
        type="button"
        onClick={onExport}
        disabled={isExporting}
        className="btn-success text-sm inline-flex items-center disabled:opacity-50"
      >
        <Download className="h-4 w-4 mr-2" />
        {isExporting ? 'Exporting...' : 'Export'}
      </button>
    </div>
  );
}
