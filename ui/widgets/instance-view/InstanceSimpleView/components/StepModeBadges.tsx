// ui/widgets/instance-view/InstanceSimpleView/components/StepModeBadges.tsx

'use client';

interface StepModeBadgesProps {
  triggerType?: string;
  executionMode?: string;
}

export function StepModeBadges({ triggerType, executionMode }: StepModeBadgesProps) {
  const isSkip = executionMode === 'skip';
  const isStop = executionMode === 'stop';
  const isManual = triggerType === 'manual';

  if (!isSkip && !isStop && !isManual) return null;

  return (
    <>
      {isManual && (
        <span className="relative group inline-flex flex-shrink-0">
          <span className="text-xs px-1.5 py-0.5 rounded bg-warning-subtle text-warning cursor-default">MANUAL</span>
          <span className="tooltip-popover tooltip-popover-warning right-0 bottom-full mb-1.5 w-36">Manual Trigger - workflow pauses before this node until Run Node.</span>
        </span>
      )}
      {isSkip && (
        <span className="relative group inline-flex flex-shrink-0">
          <span className="text-xs px-1.5 py-0.5 rounded bg-success-subtle text-success cursor-default">SKIP</span>
          <span className="tooltip-popover tooltip-popover-success right-0 bottom-full mb-1.5 w-36">Node is skipped - data passes through unchanged and execution continues.</span>
        </span>
      )}
      {isStop && (
        <span className="relative group inline-flex flex-shrink-0">
          <span className="text-xs px-1.5 py-0.5 rounded bg-danger-subtle text-danger cursor-default">STOP</span>
          <span className="tooltip-popover tooltip-popover-danger right-0 bottom-full mb-1.5 w-36">Workflow stops at this node - no further nodes will run.</span>
        </span>
      )}
    </>
  );
}

export default StepModeBadges;
