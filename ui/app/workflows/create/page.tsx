// ui/app/workflows/create/page.tsx

'use client';

import React, { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { getWorkflows } from '@/shared/api';
import type { WorkflowResponse } from '@/shared/types/api';
import { useUser } from '@/entities/user';

function WorkflowCreateContent() {
  const searchParams = useSearchParams();
  const workflowIdParam = searchParams.get('workflowId');
  const { user } = useUser();

  const [workflows, setWorkflows] = useState<WorkflowResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workflowName, setWorkflowName] = useState('');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [selectedWorkflow, setSelectedWorkflow] = useState<string>(workflowIdParam || '');
  const [creationMethod, setCreationMethod] = useState<'workflow' | 'scratch'>(
    workflowIdParam ? 'workflow' : 'scratch'
  );

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const fetchedWorkflows = await getWorkflows(user?.org_id);
        setWorkflows(fetchedWorkflows);

        if (workflowIdParam && !fetchedWorkflows.some(w => w.id === workflowIdParam)) {
          setError(`Workflow with ID ${workflowIdParam} not found`);
        }

        if (workflowIdParam) {
          const workflow = fetchedWorkflows.find(w => w.id === workflowIdParam);
          if (workflow) {
            setWorkflowName(`Copy of ${workflow.name}`);
            setWorkflowDescription(workflow.description || '');
          }
        }

        setError(null);
      } catch (err) {
        console.error('Failed to fetch data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    }

    if (user?.org_id) {
      fetchData();
    }
  }, [workflowIdParam, user?.org_id]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const params = new URLSearchParams();
    if (workflowName) params.set('name', workflowName);
    if (workflowDescription) params.set('description', workflowDescription);

    if (creationMethod === 'workflow' && selectedWorkflow) {
      params.set('from_workflow', selectedWorkflow);
    }

    const queryString = params.toString();
    window.location.href = `/workflows/builder${queryString ? `?${queryString}` : ''}`;
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-primary">Create New Workflow</h1>
        <p className="text-muted">Create a workflow from an existing workflow or from scratch</p>
      </div>

      {error && (
        <div className="mb-6 p-4 border-l-4 border-danger bg-danger-subtle text-danger">
          <p>{error}</p>
        </div>
      )}

      <div className="bg-card shadow-sm rounded-lg p-6 border border-primary">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="workflow-name" className="block text-sm font-medium text-secondary mb-1">
                Workflow Name
              </label>
              <input
                id="workflow-name"
                type="text"
                value={workflowName}
                onChange={(e) => setWorkflowName(e.target.value)}
                className="w-full p-2 border border-primary rounded bg-surface text-primary focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>

            <div>
              <label htmlFor="workflow-description" className="block text-sm font-medium text-secondary mb-1">
                Description
              </label>
              <input
                id="workflow-description"
                type="text"
                value={workflowDescription}
                onChange={(e) => setWorkflowDescription(e.target.value)}
                className="w-full p-2 border border-primary rounded bg-surface text-primary focus:ring-2 focus:ring-blue-500"
                placeholder="Optional"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-secondary mb-1">
              Creation Method
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
              <div
                className={`border rounded-lg p-4 cursor-pointer transition ${
                  creationMethod === 'workflow'
                    ? 'border-info bg-info-subtle'
                    : 'border-primary hover:bg-surface'
                }`}
                onClick={() => setCreationMethod('workflow')}
              >
                <div className="flex items-center mb-2">
                  <input
                    type="radio"
                    checked={creationMethod === 'workflow'}
                    onChange={() => setCreationMethod('workflow')}
                    className="mr-2"
                  />
                  <h3 className="font-medium text-primary">From Workflow</h3>
                </div>
                <p className="text-muted">
                  Duplicate an existing workflow
                </p>
              </div>

              <div
                className={`border rounded-lg p-4 cursor-pointer transition ${
                  creationMethod === 'scratch'
                    ? 'border-info bg-info-subtle'
                    : 'border-primary hover:bg-surface'
                }`}
                onClick={() => setCreationMethod('scratch')}
              >
                <div className="flex items-center mb-2">
                  <input
                    type="radio"
                    checked={creationMethod === 'scratch'}
                    onChange={() => setCreationMethod('scratch')}
                    className="mr-2"
                  />
                  <h3 className="font-medium text-primary">From Scratch</h3>
                </div>
                <p className="text-muted">
                  Start with a blank canvas
                </p>
              </div>
            </div>
          </div>

          {creationMethod === 'workflow' && (
            <div>
              <label className="block text-sm font-medium text-secondary mb-3">
                Select Workflow to Duplicate
              </label>

              {/* Workflows Table */}
              {workflows.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-primary">
                    <thead className="bg-card">
                      <tr>
                        <th className="w-12 px-4 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">

                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">
                          Name
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">
                          Description
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">
                          Status
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">
                          Updated
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-card divide-y divide-primary">
                      {workflows.map((workflow) => (
                        <tr
                          key={workflow.id}
                          onClick={() => setSelectedWorkflow(workflow.id)}
                          className={`cursor-pointer transition ${
                            selectedWorkflow === workflow.id
                              ? 'bg-info-subtle'
                              : 'hover:bg-surface'
                          }`}
                        >
                          <td className="px-4 py-3 whitespace-nowrap">
                            <input
                              type="radio"
                              checked={selectedWorkflow === workflow.id}
                              onChange={() => setSelectedWorkflow(workflow.id)}
                              className="h-4 w-4 text-info focus:ring-blue-500"
                            />
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className="text-sm font-medium text-primary">
                              {workflow.name}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <span className="text-sm text-secondary line-clamp-2">
                              {workflow.description || '-'}
                            </span>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                              workflow.status === 'active' || workflow.status === 'published'
                                ? 'bg-success-subtle text-success'
                                : workflow.status === 'draft'
                                ? 'bg-warning-subtle text-warning'
                                : 'bg-card text-primary dark:text-muted'
                            }`}>
                              {workflow.status || 'draft'}
                            </span>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-secondary">
                            {new Date(workflow.updated_at).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center p-8 bg-card rounded-md">
                  <p className="text-muted">
                    No workflows found
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="flex justify-end space-x-2">
            <Link
              href="/workflows"
              className="px-4 py-2 border border-primary rounded-md shadow-sm text-sm font-medium text-secondary bg-card hover:bg-surface"
            >
              Cancel
            </Link>
            <button
              type="submit"
              className="btn-primary"
              disabled={
                (creationMethod === 'workflow' && !selectedWorkflow)
              }
            >
              Create Workflow
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function WorkflowCreatePage() {
  return (
    <Suspense fallback={<div className="p-8">Loading...</div>}>
      <WorkflowCreateContent />
    </Suspense>
  );
}
