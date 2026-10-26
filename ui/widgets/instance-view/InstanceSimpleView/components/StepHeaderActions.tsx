// ui/widgets/instance-view/InstanceSimpleView/components/StepHeaderActions.tsx

"use client";

import {
  CheckCircle2,
  XCircle,
  Play,
  RotateCw,
  RefreshCw,
} from "lucide-react";
import { StatusBadge } from "@/shared/ui/Table";
import { InstanceStatus } from "@/shared/types/api";

import { StepHeaderActionsProps } from "../types";
import { StepModeBadges } from "./StepModeBadges";
import { formatDate } from '@/shared/lib/dateFormatter';

export function StepHeaderActions({
  selectedStep,
  selectedStepExecution,
  stepJobs,
  instance,
  getDisplayStatus,
  getStatusIcon,
  calculateDuration,
  approving,
  triggering,
  runningSteps,
  retryingJobs,
  onApprove,
  onTrigger,
  onRunStoppedStep,
  onRerunJobOnly,
  onRerunAndContinue,
  onRerunStepOnly,
  onCheckWebhookStatus,
  canControlRun = true,
}: StepHeaderActionsProps) {
  return (
    <div className="bg-card rounded-lg border border-primary p-4">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          {getStatusIcon(getDisplayStatus(selectedStep), "w-6 h-6")}
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-primary">
                {selectedStep.name}
              </h3>
              <StepModeBadges triggerType={selectedStep.trigger_type} executionMode={selectedStep.execution_mode} />
            </div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1">
              <StatusBadge status={getDisplayStatus(selectedStep)} />
              {(() => {
                const jobs = stepJobs.length > 0 ? stepJobs : (selectedStepExecution ? [selectedStepExecution] : []);
                const starts = jobs.map((j) => j.created_at).filter((t): t is string => !!t).sort();
                const procStarts = jobs.map((j) => j.started_at).filter((t): t is string => !!t).sort();
                const ends = jobs.map((j) => j.completed_at ?? j.updated_at).filter((t): t is string => !!t).sort();
                if (starts.length === 0) return null;
                const end = ends.length > 0 ? ends[ends.length - 1] : null;
                return (
                  <>
                    <span className="text-muted" title="Total time since queued">
                      Queued for {calculateDuration(starts[0], end)}
                    </span>
                    {procStarts.length > 0 && (
                      <>
                        <span className="text-muted">·</span>
                        <span className="text-muted" title="Processing time">
                          Processed in {calculateDuration(procStarts[0], end)}
                        </span>
                      </>
                    )}
                  </>
                );
              })()}
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {canControlRun && selectedStep.status === "waiting_for_approval" && (
            <>
              <button
                onClick={() => onApprove(false)}
                disabled={approving}
                className="btn-warning flex items-center gap-1.5 px-3! py-1.5! text-sm"
              >
                <XCircle className="w-4 h-4" />
                <span>{approving ? "..." : "Reject"}</span>
              </button>
              <button
                onClick={() => onApprove(true)}
                disabled={approving}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-success text-white text-sm rounded-md hover:bg-success disabled:opacity-50"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>{approving ? "..." : "Approve"}</span>
              </button>
            </>
          )}

          {canControlRun && selectedStep.status === "waiting_for_manual_trigger" && (
            <button
              onClick={() => onTrigger(selectedStep.step_id)}
              disabled={triggering}
              className="btn-primary text-sm flex items-center gap-1.5 px-3 py-1.5"
            >
              <Play className="w-4 h-4" />
              <span>{triggering ? "Triggering..." : "Run Node"}</span>
            </button>
          )}

          {canControlRun && selectedStep.status === "waiting_for_webhook" && selectedStep.can_check_status && (
            <button
              onClick={() => onCheckWebhookStatus(instance.id, selectedStep.step_id)}
              disabled={runningSteps.has(selectedStep.step_id)}
              className="btn-primary text-sm flex items-center gap-1.5 px-3 py-1.5"
              title="Poll the provider now for this node's pending generations"
            >
              <RefreshCw className={`w-4 h-4 ${runningSteps.has(selectedStep.step_id) ? "animate-spin" : ""}`} />
              <span>{runningSteps.has(selectedStep.step_id) ? "Checking..." : "Check Status"}</span>
            </button>
          )}

          {canControlRun && selectedStep.status === "stopped" && (
            <button
              onClick={() => onRunStoppedStep(selectedStep.step_id)}
              disabled={runningSteps.has(selectedStep.step_id)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-success text-white text-sm rounded-md hover:bg-success disabled:opacity-50"
            >
              <Play className={`w-4 h-4 ${runningSteps.has(selectedStep.step_id) ? "animate-spin" : ""}`} />
              <span>{runningSteps.has(selectedStep.step_id) ? "Running..." : "Run Node"}</span>
            </button>
          )}

          {canControlRun && selectedStepExecution && ["completed", "failed", "cancelled"].includes(selectedStepExecution.status) && ![InstanceStatus.Pending, InstanceStatus.Processing].includes(instance.status as InstanceStatus) && (
            <>
              <button
                onClick={() => onRerunAndContinue(selectedStepExecution.id)}
                disabled={retryingJobs.has(selectedStepExecution.id)}
                className="btn-primary text-sm flex items-center gap-1.5 px-3 py-1.5"
                title="Rerun this node and all downstream nodes"
              >
                <RotateCw className={`w-4 h-4 ${retryingJobs.has(selectedStepExecution.id) ? "animate-spin" : ""}`} />
                <span>Rerun</span>
              </button>
              <button
                onClick={() => onRerunStepOnly(instance.id, selectedStep.step_id)}
                disabled={runningSteps.has(selectedStep.step_id)}
                className="btn-success text-sm flex items-center gap-1.5 px-3 py-1.5"
                title="Rerun this node only (does not trigger downstream nodes)"
              >
                <RotateCw className={`w-4 h-4 ${runningSteps.has(selectedStep.step_id) ? "animate-spin" : ""}`} />
                <span>Rerun Node Only</span>
              </button>
            </>
          )}
        </div>
      </div>

      {/* Approval request shown to the approver */}
      {selectedStep.status === "waiting_for_approval" &&
        typeof selectedStep.parameters?.approval_message === "string" &&
        selectedStep.parameters.approval_message.trim() !== "" && (
          <div className="alert alert-info mb-4">
            <div className="font-medium">Approval requested</div>
            <div className="text-sm mt-1 whitespace-pre-wrap">
              {selectedStep.parameters.approval_message}
            </div>
          </div>
        )}

      {/* Error Message */}
      {selectedStepExecution?.error_message && (
        <div className="alert alert-error mb-4">
          <div className="flex items-start gap-2">
            <XCircle className="w-5 h-5 text-danger flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-medium text-danger">Error</div>
              <div className="text-sm text-danger mt-1">
                {selectedStepExecution.error_message}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Timestamps */}
      {selectedStepExecution?.started_at && (
        <div className="text-sm text-secondary space-x-4">
          <span>Started: {formatDate(selectedStepExecution.started_at)}</span>
          {selectedStepExecution.completed_at && (
            <span>Completed: {formatDate(selectedStepExecution.completed_at)}</span>
          )}
        </div>
      )}
    </div>
  );
}
