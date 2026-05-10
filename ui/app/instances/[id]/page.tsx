// ui/app/instances/[id]/page.tsx

"use client";

import { DashboardLayout } from "@/widgets/layout";
import { useOrgSettings } from "@/entities/organization";
import { useViewMode } from "@/shared/hooks/useViewMode";
import { InstanceSimpleView, MediaViewerModal } from "@/widgets/instance-view";
import type { WorkflowFormSchema } from "@/entities/workflow";
import {
  useInstanceLoader,
  useInstanceActions,
  useInstanceResources,
  useInstanceForm,
} from "./hooks";
import { coerceWorkflowSteps } from "./lib/step-utils";
import { InstanceHeader } from "./components/InstanceHeader";

export default function InstanceDetailPage() {
  // Keep org settings loaded (used by layout/child components)
  useOrgSettings();

  const { simpleMode, toggleSimpleMode } = useViewMode();

  const loader = useInstanceLoader();
  const {
    instance,
    setInstance,
    loading,
    jobs,
    setJobs,
    instanceId,
    authStatus,
    wsStatus,
    jobResources,
    setJobResources,
    loadingResources,
  } = loader;

  const actions = useInstanceActions({
    instanceId,
    instance,
    setInstance,
    jobs,
    setJobs,
    setJobResources,
  });

  const resources = useInstanceResources({
    instanceId,
    setInstance,
    jobs,
    setJobs,
    jobResources,
    setJobResources,
  });

  const form = useInstanceForm({
    instance,
    instanceId,
    setInstance,
    setJobs,
  });

  // --- Loading / auth guard screens ---

  if (loading || authStatus === "loading") {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted">Loading...</div>
        </div>
      </DashboardLayout>
    );
  }

  if (!instance) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted">Instance not found</div>
        </div>
      </DashboardLayout>
    );
  }

  // --- Derived data ---

  // Server emits InstanceResponse.steps in topological order with per-step
  // shape fields populated and status sourced from the oracle. The unified
  // StepExecution entity carries everything the UI needs, so just coerce the
  // wire DTO into the UI's WorkflowStep status-union.
  const orderedSteps = coerceWorkflowSteps(instance.steps ?? []);

  // --- Render ---

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <InstanceHeader
          instanceId={instance.id as string}
          workflowId={instance.workflow_id as string}
          wsStatus={wsStatus}
          isSimpleMode={simpleMode}
          canCancel={!!actions.canCancel}
          canRunAgain={!!actions.canRunAgain}
          updating={actions.updating}
          onCancel={actions.handleCancel}
          onRunAgain={actions.handleRunAgain}
          onToggleSimpleMode={toggleSimpleMode}
        />

        {/* Instance View */}
        <div className="bg-card rounded-lg shadow overflow-hidden" style={{ minHeight: '600px' }}>
          <InstanceSimpleView
            instance={instance}
            jobs={jobs}
            orderedSteps={orderedSteps}
            jobResources={jobResources}
            loadingResources={loadingResources}
            formSchema={form.formSchema as WorkflowFormSchema | null}
            onCancel={actions.handleCancel}
            onRunAgain={actions.handleRunAgain}
            onApprove={actions.handleApprove}
            onTrigger={actions.handleTrigger}
            onRunStoppedStep={actions.handleRunStoppedStep}
            onRetryJob={actions.handleRetryJob}
            onRerunJobOnly={actions.handleRerunJobOnly}
            onRerunAndContinue={actions.handleRerunAndContinue}
            onRerunStepOnly={actions.handleRerunStepOnly}
            onDownloadResource={resources.handleDownloadResource}
            onUploadFilesToStep={resources.handleUploadFilesToStep}
            onFormSubmit={form.handleFormSubmit}
            onRegenerateResources={resources.handleRegenerateResourcesWithIds}
            onRegenerateIteration={resources.handleRegenerateIteration}
            onDeleteResources={resources.handleDeleteResourcesWithIds}
            onUpdateJobResult={actions.handleUpdateJobResult}
            canCancel={!!actions.canCancel}
            updating={actions.updating}
            approving={actions.approving}
            triggering={actions.triggering}
            runningSteps={actions.runningSteps}
            retryingJobs={actions.retryingJobs}
            isSubmittingForm={form.isSubmittingForm}
            regeneratingResources={resources.regeneratingResources}
            deletingResources={resources.deletingResources}
            simpleMode={simpleMode}
          />
        </div>
      </div>

      {/* Media Viewer Modal */}
      {resources.viewingResource && (
        <MediaViewerModal
          resource={resources.viewingResource.resource}
          resources={resources.viewingResource.allResources}
          onClose={() => resources.setViewingResource(null)}
          onDownload={resources.handleDownloadResource}
          onNavigate={(r) =>
            resources.setViewingResource({
              resource: r,
              allResources: resources.viewingResource!.allResources,
            })
          }
        />
      )}
    </DashboardLayout>
  );
}
