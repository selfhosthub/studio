// ui/features/step-config/sections/BaseInputMappingsSection.tsx

'use client';

import React, { useState } from 'react';
import { useSharedStepConfig } from '../context/SharedStepConfigContext';

interface BaseInputMappingsSectionProps {
  title?: string;
}

export default function BaseInputMappingsSection({ title = 'Input Mappings' }: BaseInputMappingsSectionProps) {
  const {
    inputMappings,
    previousSteps,
    updateInputMapping,
    addInputMapping,
    removeInputMapping
  } = useSharedStepConfig();

  // Local state for managing UI collapse state
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  // Toggle collapse state for a specific mapping
  const toggleMappingCollapse = (paramName: string) => {
    setCollapsedSections(prev => ({
      ...prev,
      [paramName]: !prev[paramName]
    }));
  };

  return (
    <div>
      <h3 className="text-lg font-medium mb-2">{title}</h3>
      <p className="text-sm text-secondary mb-4">
        Connect this step with outputs from previous steps. These mappings will also be reflected as connection lines in the workflow diagram.
      </p>
      
      <div className="space-y-4">
        {Object.keys(inputMappings).length > 0 ? (
          Object.entries(inputMappings).map(([paramName, mapping]) => (
            <div 
              key={paramName} 
              className="border border-primary rounded-md overflow-hidden"
            >
              <div 
                className="bg-surface px-4 py-3 flex justify-between items-center cursor-pointer"
                onClick={() => toggleMappingCollapse(paramName)}
              >
                <div className="flex items-center">
                  <h4 className="font-medium">{paramName}</h4>
                  {mapping && typeof mapping === 'object' && mapping.mappingType === 'mapped' && (
                    <span className="ml-2 text-xs bg-critical-subtle text-critical px-2 py-0.5 rounded-full">
                      {previousSteps.find(step => step.id === mapping.stepId)?.name || 'Unknown'}.{mapping.outputField}
                    </span>
                  )}
                  {mapping && typeof mapping === 'object' && mapping.mappingType === 'form' && (
                    <span className="ml-2 text-xs bg-info-subtle text-info px-2 py-0.5 rounded-full">
                      Form: {mapping.formConfig?.label || paramName}
                    </span>
                  )}
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeInputMapping(paramName);
                    }}
                    className="text-danger hover:text-danger text-sm"
                  >
                    Remove
                  </button>
                  <span className="transform transition-transform duration-200">
                    {collapsedSections[paramName] ? '▼' : '▲'}
                  </span>
                </div>
              </div>
              
              {!collapsedSections[paramName] && (
                <div className="p-4 space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Mapping Type
                    </label>
                    <select
                      value={mapping.mappingType || 'mapped'}
                      onChange={(e) => {
                        const newType = e.target.value as 'mapped' | 'static' | 'form';
                        updateInputMapping(paramName, {
                          ...mapping,
                          mappingType: newType,
                          // Clear values that don't apply to the new mapping type
                          ...(newType === 'static' ? {
                            stepId: undefined,
                            source_step_id: undefined,
                            outputField: undefined,
                            source_output_field: undefined,
                          } : newType === 'form' ? {
                            // Form config is derived from parameter schema at runtime
                            stepId: undefined,
                            source_step_id: undefined,
                            outputField: undefined,
                            source_output_field: undefined,
                            staticValue: undefined,
                          } : {
                            staticValue: undefined,
                          })
                        });
                      }}
                      className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-[var(--theme-primary)] focus:border-[var(--theme-primary)]"
                    >
                      <option value="mapped">Map from previous step</option>
                      <option value="static">Static value</option>
                      <option value="form">Form input (user provides at runtime)</option>
                    </select>
                  </div>
                  
                  {/* Only show source step and output field when mapping type is 'mapped' */}
                  {(mapping.mappingType === 'mapped' || !mapping.mappingType) && (
                    <>
                      <div>
                        <label className="block text-sm font-medium mb-1">
                          Source Step
                        </label>
                        <select
                          value={mapping.stepId || mapping.source_step_id || ''}
                          onChange={(e) => {
                            updateInputMapping(paramName, {
                              ...mapping,
                              stepId: e.target.value,
                              source_step_id: e.target.value, // For backward compatibility
                              outputField: '', // Reset output field when step changes
                              source_output_field: '' // For backward compatibility
                            });
                          }}
                          className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-[var(--theme-primary)] focus:border-[var(--theme-primary)]"
                        >
                          <option value="">Select Step</option>
                          {previousSteps.map((step) => (
                            <option key={step.id} value={step.id}>
                              {step.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      
                      <div>
                        <label className="block text-sm font-medium mb-1">
                          Output Field
                        </label>
                        <select
                          value={mapping.outputField || mapping.source_output_field || ''}
                          onChange={(e) => {
                            updateInputMapping(paramName, {
                              ...mapping,
                              outputField: e.target.value,
                              source_output_field: e.target.value // For backward compatibility
                            });
                          }}
                          disabled={!mapping.stepId && !mapping.source_step_id}
                          className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-[var(--theme-primary)] focus:border-[var(--theme-primary)]"
                        >
                          <option value="">Select Output Field</option>
                          {(mapping.stepId || mapping.source_step_id) && 
                            previousSteps
                              .find((s) => s.id === (mapping.stepId || mapping.source_step_id))
                              ?.outputs && 
                            Object.keys(
                              previousSteps.find((s) => s.id === (mapping.stepId || mapping.source_step_id))
                                ?.outputs || 
                              previousSteps.find((s) => s.id === (mapping.stepId || mapping.source_step_id))
                                ?.output_fields || 
                              {}
                            ).map((field) => (
                              <option key={field} value={field}>
                                {field}
                              </option>
                            ))}
                        </select>
                      </div>
                    </>
                  )}
                  
                  {/* Only show static value field when mapping type is 'static' */}
                  {mapping.mappingType === 'static' && (
                    <div>
                      <label className="block text-sm font-medium mb-1">
                        Static Value
                      </label>
                      <input
                        type="text"
                        value={mapping.staticValue || ''}
                        onChange={(e) => {
                          updateInputMapping(paramName, {
                            ...mapping,
                            staticValue: e.target.value
                          });
                        }}
                        className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-[var(--theme-primary)] focus:border-[var(--theme-primary)]"
                        placeholder="Enter static value"
                      />
                    </div>
                  )}

                  {/* Form mode - simple message since config is derived from parameter schema */}
                  {mapping.mappingType === 'form' && (
                    <div className="p-3 bg-info-subtle border border-info rounded-md">
                      <p className="text-sm text-info">
                        User will provide this value when running the workflow.
                      </p>
                      <p className="mt-1 text-xs text-secondary">
                        Form field type and options are derived from the parameter schema.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        ) : (
          <div className="text-center py-6 text-secondary">
            <p>No input mappings defined yet.</p>
            <p className="mt-2 text-sm">
              You can add mappings here or create connections directly in the workflow diagram by dragging from one step to another.
            </p>
          </div>
        )}
        
        <div className="mt-4">
          <button
            type="button"
            onClick={() => {
              const newParamName = `param${Object.keys(inputMappings).length + 1}`;
              addInputMapping(newParamName);
            }}
            className="px-4 py-2 bg-critical text-white rounded-md hover:opacity-90 focus:outline-none"
          >
            Add Input Mapping
          </button>
        </div>
      </div>
    </div>
  );
}