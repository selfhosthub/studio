// ui/widgets/flow-editor/StepConfigPanel/components/CountdownTimer.tsx

'use client';

import React, { useEffect, useRef, useState, memo } from 'react';
import { TIMEOUTS } from '@/shared/lib/constants';

interface CountdownTimerProps {
  interval: number;
  onSave: () => void;
  onCountdownUpdate?: (countdown: number) => void;
}

// Isolated countdown timer component - only this re-renders every second
export const CountdownTimer = memo(function CountdownTimer({
  interval,
  onSave,
  onCountdownUpdate,
}: CountdownTimerProps) {
  const [countdown, setCountdown] = useState(interval * 60);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Reset countdown when interval changes
    setCountdown(interval * 60);

    // Clear any existing timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }

    // Start countdown timer
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          // Time to save
          onSave();
          return interval * 60; // Reset countdown
        }
        return prev - 1;
      });
    }, TIMEOUTS.COUNTDOWN_INTERVAL);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [interval, onSave]);

  // Notify parent of countdown for color changes (only when crossing thresholds)
  useEffect(() => {
    onCountdownUpdate?.(countdown);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- threshold expressions are intentional
  }, [countdown <= 10, countdown <= 60, onCountdownUpdate]);

  // Format countdown for display
  const formatCountdown = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <span className={`ml-1 text-xs font-mono ${
      countdown <= 10 ? 'animate-pulse' : ''
    }`}>
      {formatCountdown(countdown)}
    </span>
  );
});
