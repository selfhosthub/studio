// ui/app/workflows/builder/components/WorkflowActionButtons.tsx

'use client';

import React from 'react';
import Link from 'next/link';
import { Save } from 'lucide-react';

interface WorkflowActionButtonsProps {
  isSubmitting: boolean;
  cancelHref: string;
}

export function WorkflowActionButtons({ isSubmitting, cancelHref }: WorkflowActionButtonsProps) {
  return (
    <div className="mt-6 flex justify-end space-x-4">
      <Link
        href={cancelHref}
        className="inline-flex justify-center py-2 px-4 border border-primary shadow-sm text-sm font-medium rounded-md text-secondary bg-card hover:bg-surface"
      >
        Cancel
      </Link>
      <button
        type="submit"
        className="btn-success text-sm inline-flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
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
    </div>
  );
}
