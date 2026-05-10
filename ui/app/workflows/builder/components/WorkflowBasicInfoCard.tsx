// ui/app/workflows/builder/components/WorkflowBasicInfoCard.tsx

'use client';

import React from 'react';

interface WorkflowBasicInfoCardProps {
  name: string;
  description: string;
  status: string;
  onPropertyChange: (property: string, value: string) => void;
}

export function WorkflowBasicInfoCard({
  name,
  description,
  status,
  onPropertyChange,
}: WorkflowBasicInfoCardProps) {
  return (
    <div className="bg-card shadow-sm rounded-lg mb-6 p-4 border border-primary">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label htmlFor="workflow-name" className="block text-sm font-medium text-secondary mb-1">
            Workflow Name
          </label>
          <input
            id="workflow-name"
            type="text"
            value={name}
            onChange={(e) => onPropertyChange('name', e.target.value)}
            className="w-full p-2 border border-primary rounded-md bg-card text-primary"
            placeholder="Enter workflow name"
            required
          />
        </div>
        <div>
          <label htmlFor="workflow-status" className="block text-sm font-medium text-secondary mb-1">
            Status
          </label>
          <select
            id="workflow-status"
            className="w-full p-2 border border-primary rounded-md bg-card text-primary"
            value={status}
            onChange={(e) => onPropertyChange('status', e.target.value)}
          >
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>
        <div className="md:col-span-2">
          <label htmlFor="workflow-description" className="block text-sm font-medium text-secondary mb-1">
            Description
          </label>
          <textarea
            id="workflow-description"
            value={description}
            onChange={(e) => onPropertyChange('description', e.target.value)}
            className="w-full p-2 border border-primary rounded-md bg-card text-primary"
            rows={2}
            placeholder="Describe what this workflow does"
          />
        </div>
      </div>
    </div>
  );
}
