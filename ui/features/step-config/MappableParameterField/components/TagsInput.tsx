// ui/features/step-config/MappableParameterField/components/TagsInput.tsx

'use client';

import React, { useState, KeyboardEvent, useCallback } from 'react';
import { X } from 'lucide-react';
import { TagsInputProps } from '../types';

/**
 * Tags/chips input component for simple arrays (integers, strings)
 * Supports keyboard navigation and presets for common values
 */
export function TagsInput({ value, itemType, placeholder, paramKey, onChange }: TagsInputProps) {
  const [inputValue, setInputValue] = useState('');

  // Get presets based on param key
  const getPresets = (): (string | number)[] => {
    if (paramKey === 'success_codes') return [200, 201, 202, 204];
    if (paramKey === 'fail_codes') return [400, 401, 403, 404, 500, 502, 503];
    if (paramKey === 'fail_values') return ['error', 'failed', 'timeout'];
    return [];
  };
  const presets = getPresets();
  const availablePresets = presets.filter(p => !value.includes(p));

  const addTag = useCallback(() => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;

    let newValue: string | number = trimmed;

    // Convert to number if needed
    if (itemType === 'integer' || itemType === 'number') {
      const num = itemType === 'integer' ? parseInt(trimmed, 10) : parseFloat(trimmed);
      if (isNaN(num)) {
        setInputValue('');
        return; // Invalid number, don't add
      }
      newValue = num;
    }

    // Don't add duplicates
    if (!value.includes(newValue)) {
      onChange(paramKey, [...value, newValue]);
    }
    setInputValue('');
  }, [inputValue, itemType, value, paramKey, onChange]);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    // Enter and comma commit a tag. Tab intentionally does *not* - it must
    // remain the standard keyboard-navigation key for form usability and
    // screen readers. Earlier versions hijacked Tab and behaved
    // inconsistently depending on the surrounding form.
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTag();
    } else if (e.key === 'Backspace' && inputValue === '' && value.length > 0) {
      // Remove last tag on backspace when input is empty
      onChange(paramKey, value.slice(0, -1));
    }
  };

  const removeTag = (index: number) => {
    const newTags = [...value];
    newTags.splice(index, 1);
    onChange(paramKey, newTags);
  };

  const addPreset = (preset: string | number) => {
    if (!value.includes(preset)) {
      onChange(paramKey, [...value, preset]);
    }
  };

  return (
    <div className="flex-1 space-y-2">
      {/* Tags display + input container */}
      <div className="min-h-[42px] w-full px-2 py-1.5 bg-input border rounded-md shadow-sm focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-info flex flex-wrap gap-1.5 items-center">
        {value.map((tag: string | number, index: number) => (
          <span
            key={`${tag}-${index}`}
            className="inline-flex items-center gap-1 px-2 py-0.5 bg-surface text-primary border border-primary text-sm rounded-md"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(index)}
              className="text-muted hover:text-danger"
            >
              <X size={14} />
            </button>
          </span>
        ))}
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => addTag()}
          className="flex-1 min-w-[100px] bg-transparent border-none outline-none text-sm text-primary placeholder:text-muted"
          placeholder={value.length === 0 ? placeholder : ''}
        />
      </div>

      <p className="text-xs text-muted">Press Enter or comma to add.</p>

      {/* Preset buttons - only show if there are available presets */}
      {availablePresets.length > 0 && (
        <div className="flex flex-wrap gap-1">
          <span className="text-xs text-secondary mr-1">Add:</span>
          {availablePresets.map((preset) => (
            <button
              key={String(preset)}
              type="button"
              onClick={() => addPreset(preset)}
              className="px-2 py-0.5 text-xs bg-card hover:bg-input text-secondary rounded border border-primary"
            >
              {preset}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default TagsInput;
