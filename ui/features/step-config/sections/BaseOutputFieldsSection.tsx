// ui/features/step-config/sections/BaseOutputFieldsSection.tsx

'use client';

import React, { useState } from 'react';
import { useSharedStepConfig } from '../context/SharedStepConfigContext';

interface BaseOutputFieldsSectionProps {
  title?: string;
}

export default function BaseOutputFieldsSection({ title = 'Output Fields' }: BaseOutputFieldsSectionProps) {
  const { 
    outputFields, 
    addOutputField,
    removeOutputField 
  } = useSharedStepConfig();

  // Local state for field editing
  const [newFieldName, setNewFieldName] = useState('');
  const [newFieldPath, setNewFieldPath] = useState('');
  const [newFieldDescription, setNewFieldDescription] = useState('');
  const [editMode, setEditMode] = useState(false);
  
  // Local state for managing UI collapse state
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  // Toggle collapse state for a specific field
  const toggleFieldCollapse = (fieldName: string) => {
    setCollapsedSections(prev => ({
      ...prev,
      [fieldName]: !prev[fieldName]
    }));
  };

  // Function to update an existing field
  const updateOutputField = (fieldName: string, updates: Partial<any>) => {
    if (outputFields[fieldName]) {
      addOutputField(fieldName, {
        ...outputFields[fieldName],
        ...updates
      });
    }
  };

  // Function to add a new output field
  const handleAddField = () => {
    if (newFieldName && newFieldPath) {
      addOutputField(newFieldName, {
        path: newFieldPath,
        description: newFieldDescription || undefined
      });
      
      // Reset form fields
      setNewFieldName('');
      setNewFieldPath('');
      setNewFieldDescription('');
      setEditMode(false);
    }
  };

  return (
    <div>
      <h3 className="text-lg font-medium mb-4">{title}</h3>
      
      <div className="space-y-4">
        {Object.keys(outputFields).length > 0 ? (
          Object.entries(outputFields).map(([fieldName, field]) => (
            <div 
              key={fieldName} 
              className="border border-primary rounded-md overflow-hidden"
            >
              <div 
                className="bg-surface px-4 py-3 flex justify-between items-center cursor-pointer"
                onClick={() => toggleFieldCollapse(fieldName)}
              >
                <h4 className="font-medium">{fieldName}</h4>
                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeOutputField(fieldName);
                    }}
                    className="text-danger hover:text-danger text-sm"
                  >
                    Remove
                  </button>
                  <span className="transform transition-transform duration-200">
                    {collapsedSections[fieldName] ? '▼' : '▲'}
                  </span>
                </div>
              </div>
              
              {!collapsedSections[fieldName] && (
                <div className="p-4 space-y-4">
                  <div>
                    <label htmlFor={`output-field-path-${fieldName}`} className="block text-sm font-medium mb-1">
                      Path
                    </label>
                    <input
                      id={`output-field-path-${fieldName}`}
                      type="text"
                      value={field.path}
                      onChange={(e) => {
                        updateOutputField(fieldName, { path: e.target.value });
                      }}
                      className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-[var(--theme-primary)] focus:border-info"
                      placeholder="response.data.field"
                    />
                  </div>
                  
                  <div>
                    <label htmlFor={`output-field-desc-${fieldName}`} className="block text-sm font-medium mb-1">
                      Description (Optional)
                    </label>
                    <input
                      id={`output-field-desc-${fieldName}`}
                      type="text"
                      value={field.description || ''}
                      onChange={(e) => {
                        updateOutputField(fieldName, { description: e.target.value });
                      }}
                      className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-[var(--theme-primary)] focus:border-info"
                      placeholder="Describe what this field contains"
                    />
                  </div>
                </div>
              )}
            </div>
          ))
        ) : (
          <div className="text-center py-6 text-secondary">
            <p>No output fields defined yet. Add fields to make data available for subsequent steps.</p>
          </div>
        )}
        
        {editMode ? (
          <div className="mt-6 border border-primary rounded-md p-4 space-y-4">
            <h4 className="font-medium">Add New Output Field</h4>
            
            <div>
              <label htmlFor="new-output-field-name" className="block text-sm font-medium mb-1">
                Field Name*
              </label>
              <input
                id="new-output-field-name"
                type="text"
                value={newFieldName}
                onChange={(e) => setNewFieldName(e.target.value)}
                className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-[var(--theme-primary)] focus:border-info"
                placeholder="responseData"
              />
            </div>
            
            <div>
              <label htmlFor="new-output-field-path" className="block text-sm font-medium mb-1">
                Path*
              </label>
              <input
                id="new-output-field-path"
                type="text"
                value={newFieldPath}
                onChange={(e) => setNewFieldPath(e.target.value)}
                className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-[var(--theme-primary)] focus:border-info"
                placeholder="response.data"
              />
            </div>
            
            <div>
              <label htmlFor="new-output-field-desc" className="block text-sm font-medium mb-1">
                Description (Optional)
              </label>
              <input
                id="new-output-field-desc"
                type="text"
                value={newFieldDescription}
                onChange={(e) => setNewFieldDescription(e.target.value)}
                className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-[var(--theme-primary)] focus:border-info"
                placeholder="Describe what this field contains"
              />
            </div>
            
            <div className="flex space-x-2">
              <button
                type="button"
                onClick={handleAddField}
                disabled={!newFieldName || !newFieldPath}
                className="px-4 py-2 bg-info text-white rounded-md hover:opacity-90 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Add Field
              </button>
              <button
                type="button"
                onClick={() => {
                  setNewFieldName('');
                  setNewFieldPath('');
                  setNewFieldDescription('');
                  setEditMode(false);
                }}
                className="px-4 py-2 bg-input text-primary rounded-md hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-4">
            <button
              type="button"
              onClick={() => setEditMode(true)}
              className="px-4 py-2 bg-info text-white rounded-md hover:opacity-90 focus:outline-none"
            >
              Add Output Field
            </button>
          </div>
        )}
      </div>
    </div>
  );
}