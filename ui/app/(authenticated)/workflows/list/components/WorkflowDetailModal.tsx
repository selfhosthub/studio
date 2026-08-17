// ui/app/(authenticated)/workflows/list/components/WorkflowDetailModal.tsx

'use client';

import React from 'react';
import { Modal } from '@/shared/ui';
import type {
  MarketplaceWorkflow,
  MarketplaceWorkflowDetail,
} from '@/shared/api';

interface WorkflowDetailModalProps {
  workflow: MarketplaceWorkflow | null;
  detail: MarketplaceWorkflowDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

/**
 * Pre-install workflow preview (super-admin). Presentational only - the parent
 * fetches the full detail (step DAG, connections, credentials, I/O) lazily on
 * row-click so the catalog list stays lean at hundreds of workflows.
 */
export function WorkflowDetailModal({
  workflow,
  detail,
  loading,
  error,
  onClose,
}: WorkflowDetailModalProps) {
  const titleCase = (s: string) =>
    s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <Modal
      isOpen={!!workflow}
      onClose={onClose}
      title={workflow?.display_name ?? 'Workflow Details'} // defaults-ok
      size="lg"
    >
      {workflow && (
        <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto">
          {/* Meta */}
          <div className="flex flex-wrap gap-3 text-sm">
            <span className="badge bg-surface text-secondary">{titleCase(workflow.category)}</span>
            {workflow.version && <span className="text-muted">v{workflow.version}</span>}
            {workflow.author && <span className="text-muted">by {workflow.author}</span>}
          </div>

          {workflow.description && (
            <div>
              <h4 className="text-sm font-semibold text-primary mb-1">Description</h4>
              <p className="text-sm text-secondary">{workflow.description}</p>
            </div>
          )}

          {loading && <p className="text-sm text-muted">Loading workflow details...</p>}
          {error && <p className="text-sm text-danger">{error}</p>}

          {detail && (
            <>
              {/* Required connections */}
              {detail.connections.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-primary mb-2">Required Connections</h4>
                  <div className="space-y-2">
                    {detail.connections.map((c) => {
                      const missing = workflow.missing_packages.includes(c.provider);
                      return (
                        <div key={c.provider} className="bg-surface rounded-md p-3 text-sm">
                          <span className="font-medium text-primary">{c.provider}</span>
                          <span className={`badge ml-2 ${missing ? 'bg-warning-subtle text-warning' : 'bg-success-subtle text-success'}`}>
                            {missing ? 'Not installed' : 'Installed'}
                          </span>
                          {c.services.length > 0 && (
                            <div className="text-muted mt-1">Services: {c.services.join(', ')}</div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Required prompts */}
              {(workflow.requires_prompts ?? []).length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-primary mb-2">Required AI Prompts</h4>
                  <div className="space-y-2">
                    {(workflow.requires_prompts ?? []).map((slug) => {
                      const missing = (workflow.missing_prompts ?? []).includes(slug);
                      return (
                        <div key={slug} className="bg-surface rounded-md p-3 text-sm">
                          <span className="font-medium text-primary">{slug}</span>
                          <span className={`badge ml-2 ${missing ? 'bg-warning-subtle text-warning' : 'bg-success-subtle text-success'}`}>
                            {missing ? 'Not installed' : 'Installed'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Credentials */}
              {detail.credentials.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-primary mb-2">Credentials Needed</h4>
                  <p className="text-sm text-secondary">{detail.credentials.join(', ')}</p>
                </div>
              )}

              {/* Inputs */}
              {detail.inputs.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-primary mb-2">Inputs</h4>
                  <div className="space-y-1">
                    {detail.inputs.map((f) => (
                      <div key={f.name} className="text-sm">
                        <span className="font-medium text-primary">{f.label || f.name}</span>
                        {f.type && <span className="text-muted ml-2">({f.type})</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Outputs */}
              {detail.outputs.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-primary mb-2">Outputs</h4>
                  <p className="text-sm text-secondary">{detail.outputs.join(', ')}</p>
                </div>
              )}

              {/* Steps */}
              {detail.steps.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-primary mb-2">Steps ({detail.steps.length})</h4>
                  <div className="space-y-2">
                    {detail.steps.map((s) => (
                      <div key={s.id} className="bg-surface rounded-md p-3 text-sm">
                        <div className="font-medium text-primary">{s.name}</div>
                        {s.service && <div className="text-info">{s.service}</div>}
                        {s.depends_on.length > 0 && (
                          <div className="text-muted mt-1">After: {s.depends_on.join(', ')}</div>
                        )}
                        {s.description ? (
                          <div className="text-secondary mt-1">{s.description}</div>
                        ) : s.type ? (
                          <div className="text-muted mt-1">{titleCase(s.type)}</div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          <div className="flex justify-end pt-2 border-t border-primary">
            <button type="button" onClick={onClose} className="btn-secondary text-sm">
              Close
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
