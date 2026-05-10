// ui/shared/ui/DynamicCombobox/DynamicCombobox.tsx

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { DynamicOptionsConfig } from '@/shared/types/schema';
import type { Step } from '@/shared/types/workflow';
import { useDynamicOptions, isVariableMapping } from './hooks/useDynamicOptions';
import type { FieldOption } from './hooks/useDynamicOptions';
import { ComboboxDropdown } from './components/ComboboxDropdown';

interface DynamicComboboxProps {
  id: string;
  value: string | string[];
  onChange: (value: string | string[]) => void;
  dynamicOptions: DynamicOptionsConfig;
  providerId: string;
  credentialId?: string;
  formData: Record<string, any>;
  required?: boolean;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  multiple?: boolean;
  previousSteps?: Step[];
}

export default function DynamicCombobox({
  id,
  value,
  onChange,
  dynamicOptions,
  providerId,
  credentialId,
  formData,
  required = false,
  placeholder = 'Select or type a value...',
  className = '',
  disabled = false,
  multiple = false,
  previousSteps = [],
}: DynamicComboboxProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dropdownPosition, setDropdownPosition] = useState<{ top: number; left: number; width: number } | null>(null);

  const {
    options,
    isLoading,
    error,
    fetchOptions,
    handleLazyLoad,
    dependenciesSatisfied,
    missingDeps,
    hasDependencies,
  } = useDynamicOptions({
    credentialId,
    providerId,
    dynamicOptions,
    formData,
    previousSteps,
    value,
    multiple,
  });

  const openDropdown = useCallback(() => {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + 4,
        left: rect.left,
        width: rect.width,
      });
    }
    setIsOpen(true);
  }, []);

  const selectedValues: string[] = multiple
    ? (Array.isArray(value) ? value : (value ? [value] : []))
    : [];
  const singleValue: string = multiple ? '' : (typeof value === 'string' ? value : '');

  // "Adjust state during render" - avoids a cascading setState-in-effect.
  const [prevValue, setPrevValue] = useState(value);
  if (!multiple && value !== prevValue) {
    setPrevValue(value);
    setInputValue(typeof value === 'string' ? value : '');
  }

  // No filter when input matches current value (user just opened) or is empty - show all.
  const shouldFilter = multiple ? !!inputValue : (inputValue && inputValue !== singleValue);
  const filteredOptions = shouldFilter
    ? options.filter((option) => {
        const searchLower = inputValue.toLowerCase();
        return (
          option.label.toLowerCase().includes(searchLower) ||
          option.value.toLowerCase().includes(searchLower)
        );
      })
    : options;

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setInputValue(newValue);
    openDropdown();
    setHighlightedIndex(-1);

    if (!multiple) {
      onChange(newValue);
    }
  };

  const handleSelectOption = (option: FieldOption) => {
    if (multiple) {
      const isSelected = selectedValues.includes(option.value);
      if (isSelected) {
        onChange(selectedValues.filter(v => v !== option.value));
      } else {
        onChange([...selectedValues, option.value]);
      }
      setInputValue('');
    } else {
      setInputValue(option.label);
      onChange(option.value);
      setIsOpen(false);
    }
    setHighlightedIndex(-1);
  };

  const handleRemoveValue = (valueToRemove: string) => {
    onChange(selectedValues.filter(v => v !== valueToRemove));
  };

  const handleAddCustomValue = () => {
    if (multiple && inputValue.trim()) {
      const trimmed = inputValue.trim();
      if (!selectedValues.includes(trimmed)) {
        onChange([...selectedValues, trimmed]);
      }
      setInputValue('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (multiple && e.key === 'Backspace' && !inputValue && selectedValues.length > 0) {
      e.preventDefault();
      onChange(selectedValues.slice(0, -1));
      return;
    }

    if (!isOpen) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        openDropdown();
        e.preventDefault();
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev < filteredOptions.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : -1));
        break;
      case 'Enter':
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < filteredOptions.length) {
          handleSelectOption(filteredOptions[highlightedIndex]);
        } else if (multiple && inputValue.trim()) {
          handleAddCustomValue();
        } else {
          setIsOpen(false);
        }
        break;
      case 'Escape':
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
    }
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const getDisplayValue = () => {
    if (multiple) {
      return inputValue;
    }
    if (isVariableMapping(inputValue)) {
      return inputValue;
    }
    const matchingOption = options.find((o) => o.value === singleValue);
    return matchingOption ? matchingOption.label : inputValue;
  };

  const getLabelForValue = (val: string) => {
    const option = options.find(o => o.value === val);
    return option ? option.label : val;
  };

  const showDropdown = isOpen && !isVariableMapping(inputValue);
  const hasOptions = filteredOptions.length > 0;
  const showNoCredential = !credentialId && isOpen;
  const showNoOptions = hasOptions === false && !isLoading && !error && isOpen && !!credentialId && !!shouldFilter && !!inputValue;
  const dependencyMissing = hasDependencies && !dependenciesSatisfied;

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <div className="relative">
        {multiple && selectedValues.length > 0 && (
          <div className="flex flex-wrap gap-1 p-1 pb-0 border border-b-0 border-primary rounded-t bg-card">
            {selectedValues.map((val) => (
              <span
                key={val}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-info-subtle text-info rounded"
              >
                {getLabelForValue(val)}
                <button
                  type="button"
                  onClick={() => handleRemoveValue(val)}
                  className="hover:text-info"
                  disabled={disabled}
                >
                  <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            ))}
          </div>
        )}
        <input
          ref={inputRef}
          id={id}
          type="text"
          value={getDisplayValue()}
          onChange={handleInputChange}
          onFocus={() => { openDropdown(); handleLazyLoad(); }}
          onKeyDown={handleKeyDown}
          className={`form-input p-2 pr-8 text-sm ${
            disabled ? 'bg-card cursor-not-allowed' : ''
          } ${error ? 'border-danger' : ''} ${
            multiple && selectedValues.length > 0 ? 'rounded-b rounded-t-none' : 'rounded'
          }`}
          placeholder={multiple && selectedValues.length > 0 ? 'Add more...' : placeholder}
          required={required && (!multiple || selectedValues.length === 0)}
          disabled={disabled}
          autoComplete="off"
        />

        <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
          {isLoading && (
            <svg
              className="animate-spin h-4 w-4 text-muted"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          )}
          <button
            type="button"
            onClick={() => { if (!disabled) { if (!isOpen) { openDropdown(); handleLazyLoad(); } else { setIsOpen(false); } } }}
            className="text-muted hover:text-secondary"
            tabIndex={-1}
          >
            <svg
              className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>

      {showDropdown && dropdownPosition && (
        <ComboboxDropdown
          dropdownRef={dropdownRef}
          dropdownPosition={dropdownPosition}
          showNoCredential={showNoCredential}
          dependencyMissing={dependencyMissing}
          missingDeps={missingDeps}
          error={error}
          isLoading={isLoading}
          showNoOptions={showNoOptions}
          showHint={!isLoading && !error && !!credentialId && !dependencyMissing}
          filteredOptions={filteredOptions}
          highlightedIndex={highlightedIndex}
          multiple={multiple}
          selectedValues={selectedValues}
          singleValue={singleValue}
          onSelectOption={handleSelectOption}
          onRetry={() => fetchOptions(true)}
          onHighlight={setHighlightedIndex}
        />
      )}

      {!multiple && typeof value === 'string' && isVariableMapping(value) && (
        <div className="mt-1 text-xs text-info flex items-center gap-1">
          <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
          Using variable mapping
        </div>
      )}
    </div>
  );
}
