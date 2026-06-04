// ui/features/step-config/sections/StepInputsSection.tsx

'use client';

import React, { useState } from 'react';
import { useSharedStepConfig } from '../context/SharedStepConfigContext';
import { Tab } from '@headlessui/react';
import { PlusCircle, Database, HardDrive, ArrowLeft } from 'lucide-react';

interface StepInputsSectionProps {
  title?: string;
}

export default function StepInputsSection({ title = 'Step Inputs' }: StepInputsSectionProps) {
  const { 
    inputs,
    updateStep,
    previousSteps
  } = useSharedStepConfig();
  
  // Initialize local state
  const [activeTab, setActiveTab] = useState(0);
  const [newKeyName, setNewKeyName] = useState('');
  
  // Add a new database input
  const handleAddDatabaseInput = () => {
    if (!newKeyName) return;
    
    const newInputs = {
      ...inputs,
      database: {
        ...inputs?.database,
        [newKeyName]: {
          query: '',
          parameters: {}
        }
      }
    };
    
    updateStep({
      inputs: newInputs
    });
    
    setNewKeyName('');
  };
  
  // Add a new resource input
  const handleAddResourceInput = () => {
    if (!newKeyName) return;
    
    const newInputs = {
      ...inputs,
      resource: {
        ...inputs?.resource,
        [newKeyName]: {
          resourceId: '',
          resourceType: ''
        }
      }
    };
    
    updateStep({
      inputs: newInputs
    });
    
    setNewKeyName('');
  };
  
  // Add a new previous steps input
  const handleAddPreviousStepInput = () => {
    if (!newKeyName) return;
    
    const newInputs = {
      ...inputs,
      previous_steps: {
        ...inputs?.previous_steps,
        [newKeyName]: {
          source_step_id: '',
          output_field: ''
        }
      }
    };
    
    updateStep({
      inputs: newInputs
    });
    
    setNewKeyName('');
  };
  
  // Update a database input
  const updateDatabaseInput = (key: string, field: 'query' | 'parameters', value: any) => {
    if (!inputs?.database?.[key]) return;
    
    const newInputs = {
      ...inputs,
      database: {
        ...inputs.database,
        [key]: {
          ...inputs.database[key],
          [field]: value
        }
      }
    };
    
    updateStep({
      inputs: newInputs
    });
  };
  
  // Update a resource input
  const updateResourceInput = (key: string, field: 'resourceId' | 'resourceType', value: string) => {
    if (!inputs?.resource?.[key]) return;
    
    const newInputs = {
      ...inputs,
      resource: {
        ...inputs.resource,
        [key]: {
          ...inputs.resource[key],
          [field]: value
        }
      }
    };
    
    updateStep({
      inputs: newInputs
    });
  };
  
  // Update a previous steps input
  const updatePreviousStepInput = (key: string, field: 'source_step_id' | 'output_field' | 'transform', value: string) => {
    if (!inputs?.previous_steps?.[key]) return;
    
    const newInputs = {
      ...inputs,
      previous_steps: {
        ...inputs.previous_steps,
        [key]: {
          ...inputs.previous_steps[key],
          [field]: value
        }
      }
    };
    
    updateStep({
      inputs: newInputs
    });
  };
  
  // Delete an input
  const deleteInput = (type: 'database' | 'resource' | 'previous_steps', key: string) => {
    if (!inputs?.[type]) return;
    
    const newTypeInputs = {...inputs[type]};
    delete newTypeInputs[key];
    
    const newInputs = {
      ...inputs,
      [type]: newTypeInputs
    };
    
    updateStep({
      inputs: newInputs
    });
  };

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-medium">{title}</h3>
      
      <Tab.Group selectedIndex={activeTab} onChange={setActiveTab}>
        <Tab.List className="flex space-x-1 rounded-xl bg-info-subtle p-1">
          <Tab
            className={({ selected }) =>
              `w-full rounded-lg py-2.5 text-sm font-medium leading-5 ring-opacity-60 ring-offset-2 focus:outline-none focus:ring-2 ${
                selected
                  ? 'bg-card shadow text-info'
                  : 'text-secondary hover:bg-card/[0.12] hover:text-info'
              }`
            }
          >
            <div className="flex items-center justify-center">
              <Database size={16} className="mr-2" />
              Database
            </div>
          </Tab>
          <Tab
            className={({ selected }) =>
              `w-full rounded-lg py-2.5 text-sm font-medium leading-5 ring-opacity-60 ring-offset-2 focus:outline-none focus:ring-2 ${
                selected
                  ? 'bg-card shadow text-info'
                  : 'text-secondary hover:bg-card/[0.12] hover:text-info'
              }`
            }
          >
            <div className="flex items-center justify-center">
              <HardDrive size={16} className="mr-2" />
              Resources
            </div>
          </Tab>
          <Tab
            className={({ selected }) =>
              `w-full rounded-lg py-2.5 text-sm font-medium leading-5 ring-opacity-60 ring-offset-2 focus:outline-none focus:ring-2 ${
                selected
                  ? 'bg-card shadow text-info'
                  : 'text-secondary hover:bg-card/[0.12] hover:text-info'
              }`
            }
          >
            <div className="flex items-center justify-center">
              <ArrowLeft size={16} className="mr-2" />
              Previous Steps
            </div>
          </Tab>
        </Tab.List>
        
        <Tab.Panels className="mt-2">
          {/* Database Inputs */}
          <Tab.Panel className="rounded-xl p-3">
            <div className="space-y-4">
              {/* Add new input form */}
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Input name"
                  className="flex-1 px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
                />
                <button
                  type="button"
                  onClick={handleAddDatabaseInput}
                  disabled={!newKeyName}
                  className="btn-primary"
                >
                  <PlusCircle size={16} />
                </button>
              </div>
              
              {/* List of existing database inputs */}
              {inputs?.database && Object.entries(inputs.database).length > 0 ? (
                Object.entries(inputs.database).map(([key, dbInput]) => (
                  <div key={key} className="border border-primary rounded-md p-4 space-y-3">
                    <div className="flex justify-between items-center">
                      <h4 className="font-medium">{key}</h4>
                      <button
                        type="button"
                        onClick={() => deleteInput('database', key)}
                        className="text-danger hover:text-danger text-sm"
                      >
                        Remove
                      </button>
                    </div>
                    
                    <div>
                      <label htmlFor={`db-query-${key}`} className="block text-sm font-medium mb-1">
                        SQL Query
                      </label>
                      <textarea
                        id={`db-query-${key}`}
                        value={dbInput.query || ''}
                        onChange={(e) => updateDatabaseInput(key, 'query', e.target.value)}
                        className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
                        rows={3}
                        placeholder="SELECT * FROM table WHERE id = :id"
                      />
                    </div>
                    
                    <div>
                      <label htmlFor={`db-params-${key}`} className="block text-sm font-medium mb-1">
                        Parameters (JSON)
                      </label>
                      <textarea
                        id={`db-params-${key}`}
                        value={JSON.stringify(dbInput.parameters || {}, null, 2)}
                        onChange={(e) => {
                          try {
                            const params = JSON.parse(e.target.value);
                            updateDatabaseInput(key, 'parameters', params);
                          } catch (err) {
                            // Invalid JSON, don't update
                          }
                        }}
                        className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info font-mono text-sm"
                        rows={3}
                        placeholder='{"id": 1, "status": "active"}'
                      />
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-6 text-secondary">
                  <p>No database inputs defined yet. Add inputs to fetch data from databases.</p>
                </div>
              )}
            </div>
          </Tab.Panel>
          
          {/* Resource Inputs */}
          <Tab.Panel className="rounded-xl p-3">
            <div className="space-y-4">
              {/* Add new input form */}
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Input name"
                  className="flex-1 px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
                />
                <button
                  type="button"
                  onClick={handleAddResourceInput}
                  disabled={!newKeyName}
                  className="btn-primary"
                >
                  <PlusCircle size={16} />
                </button>
              </div>
              
              {/* List of existing resource inputs */}
              {inputs?.resource && Object.entries(inputs.resource).length > 0 ? (
                Object.entries(inputs.resource).map(([key, resource]) => (
                  <div key={key} className="border border-primary rounded-md p-4 space-y-3">
                    <div className="flex justify-between items-center">
                      <h4 className="font-medium">{key}</h4>
                      <button
                        type="button"
                        onClick={() => deleteInput('resource', key)}
                        className="text-danger hover:text-danger text-sm"
                      >
                        Remove
                      </button>
                    </div>
                    
                    <div>
                      <label htmlFor={`resource-id-${key}`} className="block text-sm font-medium mb-1">
                        Resource ID
                      </label>
                      <input
                        id={`resource-id-${key}`}
                        type="text"
                        value={resource.resourceId || ''}
                        onChange={(e) => updateResourceInput(key, 'resourceId', e.target.value)}
                        className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
                        placeholder="resource-123"
                      />
                    </div>
                    
                    <div>
                      <label htmlFor={`resource-type-${key}`} className="block text-sm font-medium mb-1">
                        Resource Type
                      </label>
                      <select
                        id={`resource-type-${key}`}
                        value={resource.resourceType || ''}
                        onChange={(e) => updateResourceInput(key, 'resourceType', e.target.value)}
                        className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
                      >
                        <option value="">Select Resource Type</option>
                        <option value="file">File</option>
                        <option value="image">Image</option>
                        <option value="document">Document</option>
                        <option value="dataset">Dataset</option>
                        <option value="model">Model</option>
                        <option value="credential">Credential</option>
                        <option value="config">Configuration</option>
                      </select>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-6 text-secondary">
                  <p>No resource inputs defined yet. Add inputs to use persisted resources.</p>
                </div>
              )}
            </div>
          </Tab.Panel>
          
          {/* Previous Steps Inputs */}
          <Tab.Panel className="rounded-xl p-3">
            <div className="space-y-4">
              {/* Add new input form */}
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Input name"
                  className="flex-1 px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
                />
                <button
                  type="button"
                  onClick={handleAddPreviousStepInput}
                  disabled={!newKeyName}
                  className="btn-primary"
                >
                  <PlusCircle size={16} />
                </button>
              </div>
              
              {/* List of existing previous steps inputs */}
              {inputs?.previous_steps && Object.entries(inputs.previous_steps).length > 0 ? (
                Object.entries(inputs.previous_steps).map(([key, stepInput]) => (
                  <div key={key} className="border border-primary rounded-md p-4 space-y-3">
                    <div className="flex justify-between items-center">
                      <h4 className="font-medium">{key}</h4>
                      <button
                        type="button"
                        onClick={() => deleteInput('previous_steps', key)}
                        className="text-danger hover:text-danger text-sm"
                      >
                        Remove
                      </button>
                    </div>
                    
                    <div>
                      <label htmlFor={`prev-step-source-${key}`} className="block text-sm font-medium mb-1">
                        Source Step
                      </label>
                      <select
                        id={`prev-step-source-${key}`}
                        value={stepInput.source_step_id || ''}
                        onChange={(e) => updatePreviousStepInput(key, 'source_step_id', e.target.value)}
                        className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
                      >
                        <option value="">Select Source Step</option>
                        {previousSteps.map(step => (
                          <option key={step.id} value={step.id}>
                            {step.name || `Step ${step.id.slice(0, 8)}`}
                          </option>
                        ))}
                      </select>
                    </div>
                    
                    <div>
                      <label htmlFor={`prev-step-output-${key}`} className="block text-sm font-medium mb-1">
                        Output Field
                      </label>
                      <input
                        id={`prev-step-output-${key}`}
                        type="text"
                        value={stepInput.output_field || ''}
                        onChange={(e) => updatePreviousStepInput(key, 'output_field', e.target.value)}
                        className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
                        placeholder="result.text"
                      />
                    </div>
                    
                    <div>
                      <label htmlFor={`prev-step-transform-${key}`} className="block text-sm font-medium mb-1">
                        Transform (optional)
                      </label>
                      <textarea
                        id={`prev-step-transform-${key}`}
                        value={stepInput.transform || ''}
                        onChange={(e) => updatePreviousStepInput(key, 'transform', e.target.value)}
                        className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info font-mono text-sm"
                        rows={3}
                        placeholder="(value) => JSON.stringify(value)"
                      />
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-6 text-secondary">
                  <p>No previous step inputs defined yet. Add inputs to use outputs from previous workflow steps.</p>
                </div>
              )}
            </div>
          </Tab.Panel>
        </Tab.Panels>
      </Tab.Group>
    </div>
  );
}