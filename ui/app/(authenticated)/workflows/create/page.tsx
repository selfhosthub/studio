// ui/app/(authenticated)/workflows/create/page.tsx

'use client';

import React, { useState, useEffect, useMemo, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { getWorkflows } from '@/shared/api';
import type { WorkflowResponse } from '@/shared/types/api';
import { useUser } from '@/entities/user';
import { ResourceTable, SearchInput } from '@/shared/ui';
import type { ResourceColumnConfig } from '@/shared/ui';
import { formatDate } from '@/shared/lib/dateFormatter';

function WorkflowCreateContent() {
  const searchParams = useSearchParams();
  const workflowIdParam = searchParams.get('workflowId');
  const { user } = useUser();

  const [workflows, setWorkflows] = useState<WorkflowResponse[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const sortedWorkflows = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    const matching = q
      ? workflows.filter(
          (w) => w.name?.toLowerCase().includes(q) || w.description?.toLowerCase().includes(q),
        )
      : workflows;
    return [...matching].sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  }, [workflows, searchTerm]);
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

  const columns: ResourceColumnConfig<WorkflowResponse>[] = [
    {
      key: 'select',
      priority: 'primary',
      header: <span className="sr-only">Select</span>,
      headerClassName: 'w-12',
      cellClassName: 'whitespace-nowrap',
      render: (workflow) => (
        <input
          type="radio"
          aria-label={`Select ${workflow.name}`}
          checked={selectedWorkflow === workflow.id}
          onChange={() => setSelectedWorkflow(workflow.id)}
          className="h-4 w-4 text-info focus:ring-blue-500"
        />
      ),
    },
    {
      key: 'name',
      header: 'Name',
      sortValue: (workflow) => workflow.name,
      render: (workflow) => (
        <span className="text-sm font-medium text-primary">
          {workflow.name}
        </span>
      ),
    },
    {
      key: 'description',
      header: 'Description',
      sortValue: (workflow) => workflow.description,
      render: (workflow) => (
        <span className="text-sm text-secondary line-clamp-2">
          {workflow.description || '-' /* defaults-ok */}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      cellClassName: 'whitespace-nowrap',
      sortValue: (workflow) => workflow.status,
      render: (workflow) => (
        <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
          workflow.status === 'active' || workflow.status === 'published'
            ? 'bg-success-subtle text-success'
            : workflow.status === 'draft'
            ? 'bg-warning-subtle text-warning'
            : 'bg-card text-primary dark:text-muted'
        }`}>
          {workflow.status || 'draft' /* defaults-ok */}
        </span>
      ),
    },
    {
      key: 'updated_at',
      header: 'Updated',
      cellClassName: 'whitespace-nowrap text-sm text-secondary',
      sortValue: (workflow) => workflow.updated_at,
      render: (workflow) => formatDate(workflow.updated_at, { time: false }),
    },
  ];

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

              <SearchInput
                value={searchTerm}
                onChange={setSearchTerm}
                placeholder="Search workflows..."
                className="mb-3"
              />

              <ResourceTable
                data={sortedWorkflows}
                getItemId={(w) => w.id}
                columns={columns}
                nameColumn="name"
                prefPage="workflows-templates"
                pagination={{ itemLabel: 'workflow' }}
                onRowClick={(w) => setSelectedWorkflow(w.id)}
                rowClassName={(w) => (selectedWorkflow === w.id ? 'bg-info-subtle' : '')}
                ariaLabel="Workflows to duplicate"
                pageResetKey={searchTerm}
                emptyState={
                  <div className="text-center p-8 bg-card rounded-md">
                    <p className="text-muted">
                      No workflows found
                    </p>
                  </div>
                }
              />
            </div>
          )}

          <div className="flex justify-end space-x-2">
            <Link
              href="/workflows"
              className="btn-cancel text-sm inline-flex items-center"
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
