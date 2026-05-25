// ui/features/maintenance/components/MaintenanceBanner.tsx

/**
 * MaintenanceBanner Component
 *
 * Displays a warning banner with countdown when maintenance mode is approaching.
 * Shows time remaining until maintenance starts.
 */

'use client';

import { useState, useEffect } from 'react';
import { TIMEOUTS } from '@/shared/lib/constants';

interface MaintenanceBannerProps {
  warningUntil: Date;
  reason?: string | null;
}

function formatTimeRemaining(ms: number): string {
  if (ms <= 0) return 'Starting now...';

  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    const remainingMinutes = minutes % 60;
    return `${hours}h ${remainingMinutes}m`;
  }
  if (minutes > 0) {
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  }
  return `${seconds}s`;
}

export default function MaintenanceBanner({ warningUntil, reason }: MaintenanceBannerProps) {
  const [timeRemaining, setTimeRemaining] = useState<number>(0);
  const [isVisible, setIsVisible] = useState(true);
  const [initialTime] = useState<number>(() => warningUntil.getTime() - Date.now());

  useEffect(() => {
    function updateCountdown() {
      const now = new Date();
      const remaining = warningUntil.getTime() - now.getTime();
      setTimeRemaining(remaining);

      // If countdown finished, the page will reload via the maintenance check
      if (remaining <= 0) {
        // Force a page refresh to trigger maintenance mode check
        window.location.reload();
      }
    }

    // Initial update
    updateCountdown();

    // Update every second
    const interval = setInterval(updateCountdown, TIMEOUTS.COUNTDOWN_INTERVAL);

    return () => clearInterval(interval);
  }, [warningUntil]);

  // Show red when under 1 minute AND initial countdown was > 1 minute
  const isUrgent = timeRemaining < 60000 && initialTime > 60000;
  // Can't dismiss when under 1 minute
  const canDismiss = timeRemaining >= 60000;

  if (!isVisible && canDismiss) return null;
  // Blink when under 30 seconds AND initial countdown was > 30 seconds
  const isCritical = timeRemaining < 30000 && timeRemaining > 0 && initialTime > 30000;

  return (
    <div className={`transition-colors duration-500 ${
      isUrgent
        ? 'bg-red-600 text-white' // css-check-ignore: solid-red-shade
        : 'bg-amber-500 text-amber-950' // css-check-ignore
    } ${isCritical ? 'animate-pulse' : ''}`}>
      <div className="px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Warning icon */}
          <svg
            className="w-5 h-5 flex-shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <span className="font-medium">
            {reason || 'Scheduled maintenance'} in{' '}
            <span className="font-bold">{formatTimeRemaining(timeRemaining)}</span>
          </span>
          <span className={`text-sm hidden sm:inline ${isUrgent ? 'text-red-200' : 'text-warning'}`  /* css-check-ignore */}>
            Please save your work.
          </span>
        </div>
        {canDismiss && (
          <button
            onClick={() => setIsVisible(false)}
            className={`p-1 rounded transition-colors${isUrgent ? 'hover:bg-red-700' : 'hover:bg-amber-600'}`} // css-check-ignore: hover state of solid banner
            aria-label="Dismiss banner"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
