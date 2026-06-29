// ui/widgets/instance-view/InstanceSimpleView/components/StepTimers.tsx

"use client";

import { useEffect, useState } from "react";
import { Timer, Cpu } from "lucide-react";
import { TIMEOUTS } from "@/shared/lib/constants";

interface StepTimersProps {
  queuedAt: string | null;
  processingStartedAt: string | null;
  end: string | null;
  calculateDuration: (start: string | null, end: string | null) => string;
}

// Queue + processing timers; ticks every second while the step is still running.
export function StepTimers({ queuedAt, processingStartedAt, end, calculateDuration }: StepTimersProps) {
  const running = end === null;
  const [, setNow] = useState(0);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow((n) => n + 1), TIMEOUTS.COUNTDOWN_INTERVAL);
    return () => clearInterval(id);
  }, [running]);

  if (!queuedAt) return null;

  return (
    <>
      <span className="inline-flex items-center gap-1 text-muted" title="Time since queued">
        <Timer className="w-3.5 h-3.5" />
        {calculateDuration(queuedAt, end)} queued
      </span>
      {processingStartedAt && (
        <span className="inline-flex items-center gap-1 text-muted" title="Processing time">
          <Cpu className="w-3.5 h-3.5" />
          {calculateDuration(processingStartedAt, end)} processing
        </span>
      )}
    </>
  );
}
