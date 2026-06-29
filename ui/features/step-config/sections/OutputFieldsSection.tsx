// ui/features/step-config/sections/OutputFieldsSection.tsx

'use client';

import React from 'react';
import { ChevronDown, ChevronUp, Plus, Trash2 } from 'lucide-react';

interface OutputFieldsSectionProps {
  outputFields: Record<string, any>;
  setOutputFields: React.Dispatch<React.SetStateAction<Record<string, any>>>;
  isExpanded: boolean;
  setIsExpanded: React.Dispatch<React.SetStateAction<boolean>>;
}

const OutputFieldsSection: React.FC<OutputFieldsSectionProps> = ({
  outputFields,
  setOutputFields,
  isExpanded,
  setIsExpanded
}) => {
  const handleAddOutputField = () => {
    const newFieldName = `output${Object.keys(outputFields).length + 1}`;
    setOutputFields({
      ...outputFields,
      [newFieldName]: { path: '', description: '', type: 'string' },
    });
  };

  const handleOutputFieldChange = (fieldName: string, key: string, value: any) => {
    setOutputFields({
      ...outputFields,
      [fieldName]: {
        ...outputFields[fieldName],
        [key]: value,
      },
    });
  };

  const handleRemoveOutputField = (fieldName: string) => {
    const newOutputFields = { ...outputFields };
    delete newOutputFields[fieldName];
    setOutputFields(newOutputFields);
  };

  return (
    <div className="mb-4">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex justify-between items-center w-full text-left py-2"
      >
        <div className="flex items-center">
          <h4 className="font-medium text-primary">Output Fields</h4>
          <span className="ml-2 text-xs text-secondary">
            {Object.keys(outputFields).length > 0 ? 
              `${Object.keys(outputFields).length} defined` : 
              'No fields'
            }
          </span>
        </div>
        {isExpanded ? (
          <ChevronUp className="h-5 w-5 text-secondary" />
        ) : (
          <ChevronDown className="h-5 w-5 text-secondary" />
        )}
      </button>
      
      {isExpanded && (
        <div className="space-y-4 mt-2">
          {Object.keys(outputFields).length > 0 ? (
            <div className="space-y-4">
              {Object.entries(outputFields).map(([fieldName, field]) => (
                <div key={fieldName} className="border rounded-md p-3 bg-surface">
                  <div className="flex justify-between items-center mb-2">
                    <input
                      type="text"
                      value={fieldName}
                      disabled
                      className="font-medium bg-transparent border-none p-0"
                      title="Field name (can't be changed after creation)"
                    />
                    <button
                      type="button"
                      onClick={() => handleRemoveOutputField(fieldName)}
                      className="p-1 text-secondary hover:text-danger"
                      aria-label="Remove field"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {/* Path */}
                    <div>
                      <label htmlFor={`path-${fieldName}`} className="block text-sm text-secondary mb-1">
                        Path
                      </label>
                      <input
                        id={`path-${fieldName}`}
                        type="text"
                        value={(field as any).path || ''}
                        onChange={(e) => handleOutputFieldChange(fieldName, 'path', e.target.value)}
                        className="form-input p-2 text-sm"
                        placeholder="data.result"
                      />
                    </div>
                    
                    {/* Type */}
                    <div>
                      <label htmlFor={`type-${fieldName}`} className="block text-sm text-secondary mb-1">
                        Type
                      </label>
                      <select
                        id={`type-${fieldName}`}
                        value={(field as any).type || 'string'}
                        onChange={(e) => handleOutputFieldChange(fieldName, 'type', e.target.value)}
                        className="form-input p-2 text-sm"
                      >
                        <option value="string">String</option>
                        <option value="number">Number</option>
                        <option value="boolean">Boolean</option>
                        <option value="object">Object</option>
                        <option value="array">Array</option>
                      </select>
                    </div>
                  </div>
                  
                  {/* Description */}
                  <div className="mt-3">
                    <label htmlFor={`desc-${fieldName}`} className="block text-sm text-secondary mb-1">
                      Description
                    </label>
                    <input
                      id={`desc-${fieldName}`}
                      type="text"
                      value={(field as any).description || ''}
                      onChange={(e) => handleOutputFieldChange(fieldName, 'description', e.target.value)}
                      className="form-input p-2 text-sm"
                      placeholder="Description of the output field"
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-secondary italic">
              No output fields defined. Add fields to expose data from this step.
            </div>
          )}
          
          <button
            type="button"
            onClick={handleAddOutputField}
            className="flex items-center text-sm text-primary hover:text-primary/80"
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Output Field
          </button>
        </div>
      )}
    </div>
  );
};

export default OutputFieldsSection;