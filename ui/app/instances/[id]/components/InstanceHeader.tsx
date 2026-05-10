// ui/app/instances/[id]/components/InstanceHeader.tsx

'use client';

import Link from 'next/link';
import { ArrowLeft, XCircle, Copy, Wifi, WifiOff, Settings2, Sparkles } from 'lucide-react';

interface InstanceHeaderProps {
  instanceId: string;
  workflowId?: string;
  wsStatus: string;
  /** True when the instance view is currently rendering in simple mode. */
  isSimpleMode: boolean;
  canCancel: boolean;
  canRunAgain: boolean;
  updating: boolean;
  onCancel: () => void;
  onRunAgain: () => void;
  onToggleSimpleMode: () => void;
}

/**
 * Header bar for the instance detail page.
 * Shows instance ID, WebSocket status indicator, a Simple/Technical mode
 * toggle, Cancel, and Run Again buttons.
 */
export function InstanceHeader({
  instanceId,
  wsStatus,
  isSimpleMode,
  canCancel,
  canRunAgain,
  updating,
  onCancel,
  onRunAgain,
  onToggleSimpleMode,
}: InstanceHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div className="flex items-center space-x-4">
        <Link
          href="/instances/list"
          className="p-2 rounded-md hover:bg-card"
        >
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-primary">
              Instance Details
            </h1>
            {/* WebSocket status indicator */}
            <div className="flex items-center gap-1 flex-shrink-0" title={wsStatus === 'connected' ? 'Live updates active' : 'Live updates disconnected'}>
              {wsStatus === 'connected' ? (
                <Wifi className="w-5 h-5 text-success" />
              ) : wsStatus === 'connecting' ? (
                <Wifi className="w-5 h-5 text-warning animate-pulse" />
              ) : (
                <WifiOff className="w-5 h-5 text-muted" />
              )}
            </div>
          </div>
          <p className="text-sm text-secondary truncate">
            ID: {instanceId}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
        {/* Simple / Technical mode toggle - always available. In technical
            mode the button shows Simple and vice versa. Toggling flips the
            `?mode=simple` query param on the current URL without unmounting
            the instance view, so WebSocket state and user scroll position
            are preserved across the switch. */}
        <button
          onClick={onToggleSimpleMode}
          className="flex items-center gap-2 px-3 sm:px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 text-sm sm:text-base" // css-check-ignore: no semantic token
          title={isSimpleMode ? "Switch to technical view" : "Switch to simple view"}
        >
          {isSimpleMode ? <Settings2 className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
          <span className="hidden sm:inline">{isSimpleMode ? "Technical" : "Simple"}</span>
          <span className="sm:hidden">{isSimpleMode ? "Tech" : "Simple"}</span>
        </button>


        {/* Cancel button - only for active/running instances */}
        {canCancel && (
          <button
            onClick={onCancel}
            disabled={updating}
            className="flex items-center gap-2 px-3 sm:px-4 py-2 bg-critical text-white rounded-md hover:bg-critical disabled:opacity-50 disabled:cursor-not-allowed text-sm sm:text-base"
          >
            <XCircle className="w-4 h-4" />
            <span className="hidden sm:inline">{updating ? 'Cancelling...' : 'Cancel'}</span>
            <span className="sm:hidden">{updating ? '...' : 'Cancel'}</span>
          </button>
        )}

        {/* Run Again button - only after the instance has finished (terminal status, no active steps) */}
        {canRunAgain && (
          <button
            onClick={onRunAgain}
            className="btn-primary flex items-center gap-2 px-3 sm:px-4 text-sm sm:text-base"
          >
            <Copy className="w-4 h-4" />
            <span>Run Again</span>
          </button>
        )}
      </div>
    </div>
  );
}
