// ui/entities/workflow/lib/can-run.ts

interface RunnableWorkflow {
  status?: string | null;
  scope?: string | null;
  created_by?: string | null;
}

/** Active workflows run for anyone; a personal draft runs only for its owner. Missing status counts as active. */
export function canRunWorkflow(workflow: RunnableWorkflow, userId?: string | null): boolean {
  const status = workflow.status ?? 'active'; // defaults-ok
  if (status === 'active') return true;
  return (
    status === 'draft' &&
    workflow.scope === 'personal' &&
    !!userId &&
    workflow.created_by === userId
  );
}
