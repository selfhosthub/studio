// ui/shared/ui/DynamicCombobox/components/ComboboxDropdown.tsx

import React from 'react';
import ReactDOM from 'react-dom';
import type { FieldOption } from '../hooks/useDynamicOptions';

interface ComboboxDropdownProps {
  dropdownRef: React.Ref<HTMLDivElement>;
  dropdownPosition: { top: number; left: number; width: number };
  // State flags
  showNoCredential: boolean;
  dependencyMissing: boolean;
  missingDeps: string[];
  error: string | null;
  isLoading: boolean;
  showNoOptions: boolean;
  showHint: boolean;
  // Options
  filteredOptions: FieldOption[];
  highlightedIndex: number;
  multiple: boolean;
  selectedValues: string[];
  singleValue: string;
  // Handlers
  onSelectOption: (option: FieldOption) => void;
  onRetry: () => void;
  onHighlight: (index: number) => void;
}

export function ComboboxDropdown({
  dropdownRef,
  dropdownPosition,
  showNoCredential,
  dependencyMissing,
  missingDeps,
  error,
  isLoading,
  showNoOptions,
  showHint,
  filteredOptions,
  highlightedIndex,
  multiple,
  selectedValues,
  singleValue,
  onSelectOption,
  onRetry,
  onHighlight,
}: ComboboxDropdownProps) {
  const hasOptions = filteredOptions.length > 0;

  return ReactDOM.createPortal(
    <div
      ref={dropdownRef}
      data-step-config-dropdown
      className="fixed z-[9999] bg-card border border-primary rounded-md shadow-lg max-h-60 overflow-auto"
      style={{ top: dropdownPosition.top, left: dropdownPosition.left, width: dropdownPosition.width }}
    >
      {/* No credential message */}
      {showNoCredential && (
        <div className="p-3 text-sm text-secondary text-center">
          Select a credential to load options
        </div>
      )}

      {/* Dependency missing message */}
      {dependencyMissing && !showNoCredential && (
        <div className="p-3 text-sm text-secondary text-center">
          Select {missingDeps.map(f => f.replace(/_/g, ' ')).join(' and ')} first
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="p-3 text-sm text-danger">
          <div className="flex items-center gap-2">
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            {error}
          </div>
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 text-info hover:text-info text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="p-3 text-sm text-secondary text-center">
          Loading options...
        </div>
      )}

      {/* Options list */}
      {!isLoading && !error && hasOptions && !dependencyMissing && (
        <ul className="py-1">
          {filteredOptions.map((option, index) => {
            const isSelected = multiple
              ? selectedValues.includes(option.value)
              : singleValue === option.value;
            return (
              <li
                key={option.value}
                onClick={() => onSelectOption(option)}
                onMouseEnter={() => onHighlight(index)}
                className={`px-3 py-2 cursor-pointer text-primary flex items-center gap-2 ${
                  highlightedIndex === index
                    ? 'bg-info-subtle text-info'
                    : 'hover:bg-surface'
                } ${isSelected && !multiple ? 'bg-info-subtle' : ''}`}
              >
                {/* Checkbox for multi-select */}
                {multiple && (
                  <span className={`flex-shrink-0 w-4 h-4 border rounded flex items-center justify-center ${ // css-check-ignore: no semantic token
                    isSelected
                      ? 'bg-blue-500 border-info text-white'
                      : 'border-primary'
                  }`}>
                    {isSelected && (
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </span>
                )}
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{option.label}</div>
                  {option.value !== option.label && (
                    <div className="text-xs text-muted dark:text-secondary truncate">{option.value}</div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* No options found */}
      {showNoOptions && !dependencyMissing && (
        <div className="p-3 text-sm text-secondary text-center">
          No matching options. You can type a custom value.
        </div>
      )}

      {/* Manual entry hint */}
      {showHint && (
        <div className="px-3 py-2 text-xs text-muted dark:text-secondary border-t border-primary bg-surface">
          Type a custom value or use {"{{variable}}"} syntax
        </div>
      )}
    </div>,
    document.body
  );
}
