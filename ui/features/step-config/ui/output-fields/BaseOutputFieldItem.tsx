// ui/features/step-config/ui/output-fields/BaseOutputFieldItem.tsx

'use client';

import React from 'react';
import { ChevronDown, ChevronRight, Trash2 } from 'lucide-react';

interface BaseOutputFieldItemProps {
  fieldKey: string;
  field: {
    path: string;
    description?: string;
    type?: string;
  };
  isCollapsed: boolean;
  onUpdate: (fieldKey: string, updatedField: any) => void;
  onRemove: (fieldKey: string) => void;
  onToggleCollapse: (fieldKey: string) => void;
  typeOptions?: { value: string; label: string }[];
}

const DEFAULT_TYPE_OPTIONS = [
  { value: 'string', label: 'String' },
  { value: 'number', label: 'Number' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'object', label: 'Object' },
  { value: 'array', label: 'Array' }
];

const BaseOutputFieldItem = React.memo(function BaseOutputFieldItem({
  fieldKey,
  field,
  isCollapsed,
  onUpdate,
  onRemove,
  onToggleCollapse,
  typeOptions = DEFAULT_TYPE_OPTIONS
}: BaseOutputFieldItemProps) {
  const handleRemove = () => {
    onRemove(fieldKey);
  };

  const handlePathChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate(fieldKey, {
      ...field,
      path: e.target.value
    });
  };

  const handleDescriptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onUpdate(fieldKey, {
      ...field,
      description: e.target.value
    });
  };

  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onUpdate(fieldKey, {
      ...field,
      type: e.target.value
    });
  };

  return (
    <div className="border rounded-md p-3 bg-card">
      <div className="flex items-center justify-between mb-2">
        <div 
          className="flex items-center cursor-pointer" 
          onClick={() => onToggleCollapse(fieldKey)}
        >
          {isCollapsed ? (
            <ChevronRight className="h-5 w-5 mr-1" />
          ) : (
            <ChevronDown className="h-5 w-5 mr-1" />
          )}
          <span className="font-medium">{fieldKey}</span>
        </div>
        <button 
          onClick={handleRemove}
          className="text-danger hover:text-danger"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {!isCollapsed && (
        <div className="space-y-4 mt-3">
          <div>
            <label className="block text-sm font-medium mb-1">Path</label>
            <input
              type="text"
              value={field.path}
              onChange={handlePathChange}
              placeholder="e.g. response.data.result"
              className="w-full p-2 border rounded-md bg-card"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <textarea
              value={field.description || ''}
              onChange={handleDescriptionChange}
              placeholder="Describe what this field represents"
              className="w-full p-2 border rounded-md bg-card min-h-[60px]"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Type</label>
            <select
              value={field.type || ''}
              onChange={handleTypeChange}
              className="w-full p-2 border rounded-md bg-card"
            >
              <option value="">Select data type</option>
              {typeOptions.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
});

export default BaseOutputFieldItem;