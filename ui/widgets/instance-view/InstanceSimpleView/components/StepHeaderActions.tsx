// ui/widgets/instance-view/InstanceSimpleView/components/StepHeaderActions.tsx

"use client";

import {
  CheckCircle2,
  XCircle,
  Play,
  RotateCw,
} from "lucide-react";
import { StatusBadge } from "@/shared/ui/Table";
import { InstanceStatus } from "@/shared/types/api";

import { StepHeaderActionsProps } from "../types";
import { StepModeBadges } from "./StepModeBadges";

export function StepHeaderActions({
  selectedStep,
  selectedStepExecution,
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
}: StepHeaderActionsProps) {
  return (
    <div className="bg-card rounded-lg border border-primary p-4">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-center gap-3">
          {getStatusIcon(getDisplayStatus(selectedStep), "w-6 h-6")}
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-primary">
                {selectedStep.name}
              </h3>
              <StepModeBadges triggerType={selectedStep.trigger_type} executionMode={selectedStep.execution_mode} />
            </div>
            <div className="flex items-center gap-2 mt-1">
              <StatusBadge status={getDisplayStatus(selectedStep)} />
              {selectedStepExecution?.started_at && (
                <span className="text-muted">
                  {calculateDuration(selectedStepExecution.started_at, selectedStepExecution.completed_at)}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {selectedStep.status === "waiting_for_approval" && (
            <>
              <button
                onClick={() => onApprove(false)}
                disabled={approving}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-danger text-white text-sm rounded-md hover:bg-danger disabled:opacity-50"
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

          {selectedStep.status === "waiting_for_manual_trigger" && (
            <button
              onClick={() => onTrigger(selectedStep.step_id)}
              disabled={triggering}
              className="btn-primary text-sm flex items-center gap-1.5 px-3 py-1.5"
            >
              <Play className="w-4 h-4" />
              <span>{triggering ? "Triggering..." : "Run Step"}</span>
            </button>
          )}

          {selectedStep.status === "stopped" && (
            <button
              onClick={() => onRunStoppedStep(selectedStep.step_id)}
              disabled={runningSteps.has(selectedStep.step_id)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-success text-white text-sm rounded-md hover:bg-success disabled:opacity-50"
            >
              <Play className={`w-4 h-4 ${runningSteps.has(selectedStep.step_id) ? "animate-spin" : ""}`} />
              <span>{runningSteps.has(selectedStep.step_id) ? "Running..." : "Run Step"}</span>
            </button>
          )}

          {selectedStepExecution && ["completed", "failed", "cancelled"].includes(selectedStepExecution.status) && ![InstanceStatus.Pending, InstanceStatus.Processing].includes(instance.status as InstanceStatus) && (
            <>
              <button
                onClick={() => onRerunAndContinue(selectedStepExecution.id)}
                disabled={retryingJobs.has(selectedStepExecution.id)}
                className="btn-primary text-sm flex items-center gap-1.5 px-3 py-1.5"
                title="Rerun this step and all downstream steps"
              >
                <RotateCw className={`w-4 h-4 ${retryingJobs.has(selectedStepExecution.id) ? "animate-spin" : ""}`} />
                <span>Rerun</span>
              </button>
              <button
                onClick={() => onRerunStepOnly(instance.id, selectedStep.step_id)}
                disabled={runningSteps.has(selectedStep.step_id)}
                className="btn-success text-sm flex items-center gap-1.5 px-3 py-1.5"
                title="Rerun this step only (does not trigger downstream steps)"
              >
                <RotateCw className={`w-4 h-4 ${runningSteps.has(selectedStep.step_id) ? "animate-spin" : ""}`} />
                <span>Rerun Step Only</span>
              </button>
            </>
          )}
        </div>
      </div>

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
          <span>Started: {new Date(selectedStepExecution.started_at).toLocaleString()}</span>
          {selectedStepExecution.completed_at && (
            <span>Completed: {new Date(selectedStepExecution.completed_at).toLocaleString()}</span>
          )}
        </div>
      )}
    </div>
  );
}
