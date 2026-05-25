// ui/app/run/[workflowId]/page.tsx

"use client";

/**
 * Pre-run form page for a workflow.
 *
 * Loads the workflow metadata and its server-derived form schema, renders the
 * PreRunForm accordion, then creates + starts an instance on submit and
 * redirects to the instance page (which defaults to simple view).
 *
 * Everything downstream of Start lives in the technical instance view
 * (InstanceSimpleView) with `simpleMode` toggled on - there is no separate
 * ExperienceView state machine anymore.
 */

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useUser } from "@/entities/user";
import { DashboardLayout } from "@/widgets/layout";
import {
  createInstance,
  getWorkflow,
  getWorkflowFormSchema,
  startInstance,
  submitFormAndStart,
  WorkflowFormSchemaResponse,
} from "@/shared/api";
import PreRunForm from "./components/PreRunForm";

export default function RunWorkflowPage() {
  const params = useParams();
  const router = useRouter();
  const { status: authStatus } = useUser();

  const workflowId = params?.workflowId as string;

  const [workflow, setWorkflow] = useState<Awaited<ReturnType<typeof getWorkflow>> | null>(null);
  const [formSchema, setFormSchema] = useState<WorkflowFormSchemaResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (authStatus === "loading") return;
    if (authStatus === "unauthenticated") {
      router.push("/login");
      return;
    }

    const loadWorkflow = async () => {
      setLoading(true);
      try {
        const [workflowData, schemaData] = await Promise.all([
          getWorkflow(workflowId),
          getWorkflowFormSchema(workflowId).catch(() => null),
        ]);
        setWorkflow(workflowData);
        setFormSchema(schemaData);
      } catch (err: unknown) {
        console.error("Failed to load workflow:", err);
        setError(err instanceof Error ? err.message : "Failed to load workflow");
      } finally {
        setLoading(false);
      }
    };

    loadWorkflow();
  }, [workflowId, authStatus, router]);

  const handleSubmit = async (formValues: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      const instance = await createInstance(workflowId, formValues, {
        source: "run_page",
      });

      const hasFormValues = formValues && Object.keys(formValues).length > 0;
      if (hasFormValues) {
        await submitFormAndStart(instance.id, formValues);
      } else {
        await startInstance(instance.id);
      }

      router.push(`/instances/${instance.id}`);
    } catch (err: unknown) {
      console.error("Failed to create/start instance:", err);
      setError(err instanceof Error ? err.message : "Failed to start workflow");
      setSubmitting(false);
    }
  };

  if (loading || authStatus === "loading") {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted">Loading...</div>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="text-danger mb-4">{error}</div>
            <button
              onClick={() => router.back()}
              className="text-info hover:underline"
            >
              Go back
            </button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (!workflow) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted">Workflow not found</div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <PreRunForm
        workflowName={(workflow.name as string) || "Run Workflow"}
        workflowDescription={workflow.description as string | undefined}
        formSchema={formSchema}
        submitting={submitting}
        onSubmit={handleSubmit}
      />
    </DashboardLayout>
  );
}
