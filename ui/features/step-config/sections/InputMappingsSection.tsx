// ui/features/step-config/sections/InputMappingsSection.tsx

'use client';

import React from 'react';
import { Step } from '@/entities/workflow';
import { Plus, Trash2 } from 'lucide-react';

interface InputMapping {
  mappingType?: 'mapped' | 'static';
  stepId?: string;
  outputField?: string;
  staticValue?: string;
}

interface InputMappingsSectionProps {
  inputMappings: Record<string, InputMapping>;
  paramSchema: any;
  previousSteps: Step[];
  setInputMappings: React.Dispatch<React.SetStateAction<Record<string, InputMapping>>>;
  isExpanded: boolean;
  setIsExpanded: React.Dispatch<React.SetStateAction<boolean>>;
  // New props for connection syncing
  stepId?: string; // Current step ID
  onConnectionsChange?: (connections: any[]) => void; // Callback to update connections
  connections?: any[]; // Current connections
}

const InputMappingsSection: React.FC<InputMappingsSectionProps> = ({
  inputMappings,
  paramSchema,
  previousSteps,
  setInputMappings,
  isExpanded,
  setIsExpanded,
  stepId,
  onConnectionsChange,
  connections = []
}) => {
  // Handle adding a new input mapping
  const handleAddInputMapping = () => {
    // Create a default parameterPath based on the first parameter from schema
    let defaultPath = '';
    if (paramSchema && paramSchema.properties) {
      // Get all available parameter keys from schema
      const paramKeys = Object.keys(paramSchema.properties);
      
      // Filter out keys that already have mappings
      const availableParams = paramKeys.filter(key => !inputMappings[key]);
      
      // If there are still unmapped parameters, use the first one
      if (availableParams.length > 0) {
        defaultPath = availableParams[0];
      } else if (paramKeys.length > 0) {
        // If all parameters are mapped, create a new unique name
        const baseKey = paramKeys[0];
        let counter = 1;
        while (inputMappings[`${baseKey}_${counter}`]) {
          counter++;
        }
        defaultPath = `${baseKey}_${counter}`;
      } else {
        // Fallback if no parameters defined in schema
        defaultPath = `param_${Object.keys(inputMappings).length + 1}`;
      }
    } else {
      // Fallback if no schema is available
      defaultPath = `param_${Object.keys(inputMappings).length + 1}`;
    }
    
    // Look for matching outputs from previous steps for auto-detection
    let matchingOutput = null;
    let matchingStepId = '';
    
    // Try to find a matching output field from previous steps based on name
    if (previousSteps.length > 0 && defaultPath) {
      for (const prevStep of previousSteps) {
        if (prevStep.outputs) {
          // Check for exact match first
          const exactMatch = Object.keys(prevStep.outputs).find(
            outputKey => outputKey.toLowerCase() === defaultPath.toLowerCase()
          );
          
          if (exactMatch) {
            matchingOutput = exactMatch;
            matchingStepId = prevStep.id;
            break;
          }
          
          // If no exact match, look for a field that contains the parameter name
          const partialMatch = Object.keys(prevStep.outputs).find(
            outputKey => outputKey.toLowerCase().includes(defaultPath.toLowerCase())
          );
          
          if (partialMatch) {
            matchingOutput = partialMatch;
            matchingStepId = prevStep.id;
            break;
          }
        }
      }
    }
    
    // Create a new mapping with the selected parameter path
    const newInputMappings: Record<string, InputMapping> = {
      ...inputMappings,
      [defaultPath]: {
        mappingType: 'mapped',
        stepId: matchingStepId || '',
        outputField: matchingOutput || '',
        staticValue: '',
      },
    };
    
    // Update the state with the new mappings
    setInputMappings(newInputMappings);
    
    // If we have an auto-matched mapping with a source step, create a connection
    if (matchingStepId && matchingOutput && stepId && onConnectionsChange) {
      syncConnectionsWithMappings(newInputMappings, '', matchingStepId);
    }
  };

  const handleInputMappingChange = (
    paramPath: string,
    key: string,
    value: any
  ) => {
    let updatedMapping: InputMapping;
    let prevMapping = inputMappings[paramPath];
    let prevStepId = prevMapping?.stepId || '';
    let shouldSyncConnections = false;
    
    // If changing mapping type, initialize the other fields appropriately
    if (key === 'mappingType') {
      if (value === 'static') {
        // When switching to static, set an empty value and clear step mappings
        // If we had a valid stepId before, we need to remove the connection
        shouldSyncConnections = prevMapping?.mappingType === 'mapped' && prevStepId !== '';
        
        updatedMapping = {
          ...prevMapping,
          mappingType: 'static',
          staticValue: '',
          stepId: '',
          outputField: ''
        };
      } else {
        // When switching to mapped, clear static value
        updatedMapping = {
          ...prevMapping,
          mappingType: 'mapped',
          staticValue: '',
          stepId: prevMapping?.stepId || '',
          outputField: prevMapping?.outputField || ''
        };
      }
    } else if (key === 'stepId') {
      // When changing step ID, we need to update connections
      shouldSyncConnections = true;
      
      updatedMapping = {
        ...prevMapping,
        [key]: value,
        // Reset output field when changing step
        outputField: ''
      };
    } else {
      // For other changes, just update the specific field
      // If changing outputField and we have a stepId, sync connections
      if (key === 'outputField' && prevMapping?.stepId) {
        shouldSyncConnections = true;
      }
      
      updatedMapping = {
        ...prevMapping,
        [key]: value,
      };
    }
    
    // Update input mappings
    const newInputMappings = {
      ...inputMappings,
      [paramPath]: updatedMapping,
    };
    
    setInputMappings(newInputMappings);
    
    // Sync connections if needed and if we have the necessary props
    if (shouldSyncConnections && stepId && onConnectionsChange) {
      syncConnectionsWithMappings(newInputMappings, prevStepId, updatedMapping.stepId ?? '');
    }
  };
  
  // Function to sync connections when mappings change
  const syncConnectionsWithMappings = (
    newMappings: Record<string, any>,
    prevSourceId: string,
    currentSourceId: string
  ) => {
    if (!stepId || !onConnectionsChange) return;
    
    // Get all connections that involve this step
    const existingConnections = [...connections];
    
    // First, remove any connection where this step is the target and the source is the previous stepId
    // (this handles removing or changing source step ID)
    const connectionsWithoutPrev = existingConnections.filter(conn => {
      // Keep all connections that don't involve this specific mapping
      // (either different target or source than what we're changing)
      return !(conn.target_id === stepId && conn.source_id === prevSourceId);
    });
    
    // Now add a new connection if we have a valid mapping
    if (currentSourceId && currentSourceId !== '') {
      // Check if we already have this connection
      const connectionExists = connectionsWithoutPrev.some(
        conn => conn.source_id === currentSourceId && conn.target_id === stepId
      );
      
      // Only add if the connection doesn't exist
      if (!connectionExists) {
        const newConnection = {
          id: `conn-${currentSourceId}-${stepId}`,
          source_id: currentSourceId,
          target_id: stepId
        };
        
        connectionsWithoutPrev.push(newConnection);
      }
    }
    
    // Update connections if they've changed
    if (JSON.stringify(connectionsWithoutPrev) !== JSON.stringify(existingConnections)) {
      onConnectionsChange(connectionsWithoutPrev);
    }
  };

  const handleRemoveInputMapping = (paramPath: string) => {
    // Store the mapping details before removing it
    const mapping = inputMappings[paramPath];
    const sourceStepId = mapping?.stepId;
    const isMapped = mapping?.mappingType === 'mapped';
    
    // Remove the mapping
    const newInputMappings = { ...inputMappings };
    delete newInputMappings[paramPath];
    setInputMappings(newInputMappings);
    
    // If it was a mapped input with a valid source step, we might need to update connections
    if (isMapped && sourceStepId && stepId && onConnectionsChange) {
      // Check if there are other mappings from the same source step
      const hasOtherMappingsFromSameSource = Object.values(newInputMappings).some(
        mapping => mapping.mappingType === 'mapped' && mapping.stepId === sourceStepId
      );
      
      // If there are no other mappings from this source step, remove the connection
      if (!hasOtherMappingsFromSameSource) {
        syncConnectionsWithMappings(newInputMappings, sourceStepId, '');
      }
    }
  };

  return (
    <div className="mb-4 border border-critical rounded-md overflow-hidden">
      {/* Header section */}
      <div
        className="flex justify-between items-center cursor-pointer p-3 bg-critical text-white"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <h3 className="text-md font-medium">Input Mappings</h3>
        <span>{isExpanded ? '▼' : '►'}</span>
      </div>
      
      {/* Content section (only shown when expanded) */}
      {isExpanded && (
        <div className="p-4 bg-card">
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-secondary">
              Map inputs from previous step outputs or set static values
            </p>
            <button
              type="button"
              onClick={handleAddInputMapping}
              disabled={!paramSchema}
              className="px-3 py-1 text-sm bg-critical text-white rounded-md hover:opacity-90
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="flex items-center">
                <Plus className="h-4 w-4 mr-1" />
                Add Mapping
              </span>
            </button>
          </div>
          
          {/* Mappings list */}
          {Object.keys(inputMappings).length > 0 ? (
            <div className="space-y-4">
              {Object.entries(inputMappings).map(([paramPath, mapping]) => (
                <div key={paramPath} className="border border-critical rounded-md p-4 bg-critical-subtle">
                  <div className="flex justify-between items-center mb-3">
                    <h4 className="font-medium text-primary">{paramPath}</h4>
                    <button
                      type="button"
                      onClick={() => handleRemoveInputMapping(paramPath)}
                      className="text-danger hover:text-danger"
                      aria-label="Remove mapping"
                    >
                      <Trash2 className="h-5 w-5" />
                    </button>
                  </div>
                  
                  {/* Mapping type selection */}
                  <div className="mb-4">
                    <label htmlFor={`mapping-type-${paramPath}`} className="block text-sm font-medium text-secondary mb-1">
                      Mapping Type
                    </label>
                    <select
                      id={`mapping-type-${paramPath}`}
                      value={mapping.mappingType || 'mapped'}
                      onChange={(e) => handleInputMappingChange(paramPath, 'mappingType', e.target.value)}
                      className="form-input p-2 text-sm"
                    >
                      <option value="mapped">Mapped from Output</option>
                      <option value="static">Static Value</option>
                    </select>
                  </div>
                  
                  {/* Render different fields based on mapping type */}
                  {mapping.mappingType === 'static' ? (
                    <div>
                      <label htmlFor={`static-value-${paramPath}`} className="block text-sm font-medium text-secondary mb-1">
                        Static Value
                      </label>
                      <input
                        id={`static-value-${paramPath}`}
                        type="text"
                        value={mapping.staticValue || ''}
                        onChange={(e) => handleInputMappingChange(paramPath, 'staticValue', e.target.value)}
                        className="form-input p-2 text-sm"
                        placeholder="Enter a static value"
                      />
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {/* Source step selection */}
                      <div>
                        <label htmlFor={`step-${paramPath}`} className="block text-sm font-medium text-secondary mb-1">
                          Source Step
                        </label>
                        <select
                          id={`step-${paramPath}`}
                          value={mapping.stepId || ''}
                          onChange={(e) => handleInputMappingChange(paramPath, 'stepId', e.target.value)}
                          className="form-input p-2 text-sm"
                        >
                          <option value="">Select a step</option>
                          {previousSteps.map((step) => (
                            <option key={step.id} value={step.id}>
                              {step.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      
                      {/* Output field selection */}
                      <div>
                        <label htmlFor={`output-${paramPath}`} className="block text-sm font-medium text-secondary mb-1">
                          Output Field
                        </label>
                        <select
                          id={`output-${paramPath}`}
                          value={mapping.outputField || ''}
                          onChange={(e) => handleInputMappingChange(paramPath, 'outputField', e.target.value)}
                          disabled={!mapping.stepId}
                          className="form-input p-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <option value="">Select an output field</option>
                          {mapping.stepId &&
                            previousSteps
                              .find(step => step.id === mapping.stepId)
                              ?.outputs &&
                            Object.keys(
                              previousSteps.find(step => step.id === mapping.stepId)?.outputs || {}
                            ).map((field) => (
                              <option key={field} value={field}>
                                {field}
                              </option>
                            ))}
                        </select>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-6 bg-surface rounded-md">
              <p className="text-muted">
                No input mappings defined yet.
              </p>
              <p className="text-sm text-secondary mt-1">
                Add a mapping to connect this step with previous steps.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default InputMappingsSection;
