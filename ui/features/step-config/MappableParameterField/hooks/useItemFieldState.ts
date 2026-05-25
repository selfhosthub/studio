// ui/features/step-config/MappableParameterField/hooks/useItemFieldState.ts

import { useState, useEffect } from 'react';
import type { FieldMode, InputMapping } from '../types';

interface ItemFieldMapping {
  stepId: string;
  outputField: string;
  loop?: boolean;
}

interface InitializedState {
  modes: Record<string, FieldMode>;
  mappings: Record<string, ItemFieldMapping>;
}

/**
 * Hook to manage field modes and mappings within array items.
 * Detects template strings in values and initializes the appropriate states.
 * Also checks parent inputMappings for saved form mappings.
 */
export function useItemFieldState(
  value: any,
  paramKey: string,
  allInputMappings: Record<string, InputMapping> = {}
) {
  // Initialize field states by scanning for template strings and checking parent inputMappings
  const initializeFieldStates = (): InitializedState => {
    const modes: Record<string, FieldMode> = {};
    const mappings: Record<string, ItemFieldMapping> = {};

    // Also scan allInputMappings directly - some mappings (form, prompt)
    // are set before the user has typed any value into the field, so the
    // field may not yet be a key on the item object. The per-item scan
    // below would then miss them and reset the mode to 'static' on the
    // next render. Pull in any mapping whose path matches this paramKey
    // up-front.
    const topLevelPrefix = `${paramKey}[`;
    for (const [key, savedMapping] of Object.entries(allInputMappings)) {
      if (!key.startsWith(topLevelPrefix)) continue;
      // Parse "paramKey[i].field" or "paramKey[i].field[j].nestedField"
      const rest = key.slice(topLevelPrefix.length);
      const topClose = rest.indexOf(']');
      if (topClose < 0) continue;
      const itemIndex = parseInt(rest.slice(0, topClose), 10);
      if (isNaN(itemIndex)) continue;
      const afterIndex = rest.slice(topClose + 1); // ".field" or ".field[j].nested"
      if (!afterIndex.startsWith('.')) continue;
      const fieldPart = afterIndex.slice(1);
      // Skip deeply nested - handled by the nested scan below
      if (fieldPart.includes('[') || fieldPart.includes('.')) continue;
      const stateKey = `${itemIndex}:${fieldPart}`;
      if (savedMapping?.mappingType === 'form') {
        modes[stateKey] = 'form';
      } else if (savedMapping?.mappingType === 'prompt') {
        modes[stateKey] = 'prompt';
      } else if (savedMapping?.mappingType === 'mapped' && savedMapping.stepId && savedMapping.outputField) {
        modes[stateKey] = 'mapped';
        mappings[stateKey] = {
          stepId: savedMapping.stepId,
          outputField: savedMapping.outputField,
          loop: savedMapping.loop,
        };
      }
    }

    if (Array.isArray(value)) {
      value.forEach((item, itemIndex) => {
        if (typeof item === 'object' && item !== null) {
          Object.entries(item).forEach(([fieldKey, fieldValue]) => {
            const key = `${itemIndex}:${fieldKey}`;

            // First check if there's a saved mapping in parent inputMappings
            // Array-indexed parameters use the format: paramKey[itemIndex].fieldKey
            const nestedParamKey = `${paramKey}[${itemIndex}].${fieldKey}`;
            const savedMapping = allInputMappings[nestedParamKey];

            if (savedMapping?.mappingType === 'form') {
              modes[key] = 'form';
            } else if (savedMapping?.mappingType === 'prompt') {
              modes[key] = 'prompt';
            } else if (savedMapping?.mappingType === 'mapped' && savedMapping.stepId && savedMapping.outputField) {
              modes[key] = 'mapped';
              mappings[key] = {
                stepId: savedMapping.stepId,
                outputField: savedMapping.outputField,
                loop: savedMapping.loop,
              };
            }
            // If no saved mapping, check if the value is a template string like {{ stepId.outputField }} or {{ steps.stepId.outputField }}
            else if (typeof fieldValue === 'string') {
              const templateMatch = fieldValue.match(/^\{\{\s*(?:steps\.)?([\w-]+)\.(.+?)\s*\}\}$/);
              if (templateMatch) {
                modes[key] = 'mapped';
                mappings[key] = {
                  stepId: templateMatch[1],
                  outputField: templateMatch[2],
                };
              }
            } else if (Array.isArray(fieldValue)) {
              // Recursively scan nested arrays (e.g., elements within scenes)
              const nestedKeyPrefix = `${paramKey}:${itemIndex}:${fieldKey}`;
              fieldValue.forEach((nestedItem, nestedIdx) => {
                if (typeof nestedItem === 'object' && nestedItem !== null) {
                  Object.entries(nestedItem).forEach(([nestedKey, nestedValue]) => {
                    const nestedKeyPath = `${nestedKeyPrefix}:${nestedIdx}:${nestedKey}`;

                    // Check for saved mapping in parent inputMappings for nested arrays
                    const nestedParamKey = `${paramKey}[${itemIndex}].${fieldKey}[${nestedIdx}].${nestedKey}`;
                    const savedNestedMapping = allInputMappings[nestedParamKey];

                    if (savedNestedMapping?.mappingType === 'form') {
                      modes[nestedKeyPath] = 'form';
                    } else if (savedNestedMapping?.mappingType === 'prompt') {
                      modes[nestedKeyPath] = 'prompt';
                    } else if (savedNestedMapping?.mappingType === 'mapped' && savedNestedMapping.stepId && savedNestedMapping.outputField) {
                      modes[nestedKeyPath] = 'mapped';
                      mappings[nestedKeyPath] = {
                        stepId: savedNestedMapping.stepId,
                        outputField: savedNestedMapping.outputField,
                        loop: savedNestedMapping.loop,
                      };
                    }
                    // If no saved mapping, check if the value is a template string
                    else if (typeof nestedValue === 'string') {
                      const templateMatch = nestedValue.match(/^\{\{\s*(?:steps\.)?(\w+)\.(.+?)\s*\}\}$/);
                      if (templateMatch) {
                        modes[nestedKeyPath] = 'mapped';
                        mappings[nestedKeyPath] = {
                          stepId: templateMatch[1],
                          outputField: templateMatch[2],
                        };
                      }
                    }
                  });
                }
              });
            }
          });
        }
      });
    }

    return { modes, mappings };
  };

  const { modes: initialModes, mappings: initialMappings } = initializeFieldStates();

  const [itemFieldModes, setFieldModes] = useState<Record<string, FieldMode>>(initialModes);
  const [itemFieldMappings, setItemFieldMappings] = useState<Record<string, ItemFieldMapping>>(initialMappings);
  const [showItemModeDropdown, setShowItemModeDropdown] = useState<string | null>(null);

  // Re-initialize when value changes externally.
  // Use modes/mappings from initializeFieldStates as the source of truth -
  // all user-initiated mode changes are already synced to allInputMappings
  // via onMappingChange, so initializeFieldStates picks them up.
  // The old merge logic kept stale index-based entries after array reorders.
  useEffect(() => {
    const { modes, mappings } = initializeFieldStates();

    setFieldModes(prev => {
      // Check if anything actually changed to avoid unnecessary re-renders
      const prevKeys = Object.keys(prev);
      const newKeys = Object.keys(modes);
      if (prevKeys.length === newKeys.length && newKeys.every(k => prev[k] === modes[k])) {
        return prev;
      }
      return modes;
    });
    setItemFieldMappings(prev => {
      const newKeys = Object.keys(mappings);
      const prevKeys = Object.keys(prev);
      if (prevKeys.length === newKeys.length && newKeys.every(k =>
        prev[k]?.stepId === mappings[k]?.stepId && prev[k]?.outputField === mappings[k]?.outputField
      )) {
        return prev;
      }
      return mappings;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-initialize when external value changes; initializeFieldStates is intentionally excluded to avoid loops since it reads from value
  }, [value]);

  // Get field mode for an array item field
  const getItemFieldMode = (itemIndex: number, fieldKey: string, keyPrefix?: string): FieldMode => {
    const key = keyPrefix ? `${keyPrefix}:${itemIndex}:${fieldKey}` : `${itemIndex}:${fieldKey}`;
    return itemFieldModes[key] || 'static';
  };

  // Set field mode for an array item field
  const setItemFieldMode = (
    itemIndex: number,
    fieldKey: string,
    mode: FieldMode,
    keyPrefix?: string,
    onMappingChange?: (key: string, mapping: any) => void
  ) => {
    const key = keyPrefix ? `${keyPrefix}:${itemIndex}:${fieldKey}` : `${itemIndex}:${fieldKey}`;
    setFieldModes(prev => ({ ...prev, [key]: mode }));
    setShowItemModeDropdown(null);

    const nestedParamKey = `${paramKey}[${itemIndex}].${fieldKey}`;

    if (mode === 'mapped') {
      // Initialize with empty mapping
      setItemFieldMappings(prev => ({ ...prev, [key]: { stepId: '', outputField: '' } }));
    } else if (mode === 'form' && onMappingChange) {
      // Propagate form mode to parent via onMappingChange
      onMappingChange(nestedParamKey, { mappingType: 'form' });
    } else if (mode === 'prompt' && onMappingChange) {
      // Propagate prompt mode to parent (same pattern as form)
      onMappingChange(nestedParamKey, { mappingType: 'prompt', promptId: '', variableValues: {} });
    } else if (mode === 'static' && onMappingChange) {
      // Remove any non-static mapping when switching back
      onMappingChange(nestedParamKey, null);
    }
  };

  // Get mapping for an array item field
  const getItemFieldMapping = (itemIndex: number, fieldKey: string, keyPrefix?: string) => {
    const key = keyPrefix ? `${keyPrefix}:${itemIndex}:${fieldKey}` : `${itemIndex}:${fieldKey}`;
    return itemFieldMappings[key] || { stepId: '', outputField: '' };
  };

  // Set mapping for an array item field
  const setItemFieldMapping = (
    itemIndex: number,
    fieldKey: string,
    mapping: ItemFieldMapping,
    keyPrefix?: string
  ) => {
    const key = keyPrefix ? `${keyPrefix}:${itemIndex}:${fieldKey}` : `${itemIndex}:${fieldKey}`;
    setItemFieldMappings(prev => ({ ...prev, [key]: mapping }));
  };

  // Get nested array mappings for iteration detection
  const getNestedArrayMappings = (isIterable: boolean, isComplexArray: boolean): ItemFieldMapping[] => {
    if (!isIterable || !isComplexArray) return [];

    const mappingsWithArrayPaths: ItemFieldMapping[] = [];
    for (const [_key, mapping] of Object.entries(initialMappings)) {
      if (mapping.outputField?.includes('[*]')) {
        mappingsWithArrayPaths.push(mapping);
      }
    }
    return mappingsWithArrayPaths;
  };

  return {
    itemFieldModes,
    itemFieldMappings,
    showItemModeDropdown,
    setShowItemModeDropdown,
    getItemFieldMode,
    setItemFieldMode,
    getItemFieldMapping,
    setItemFieldMapping,
    getNestedArrayMappings,
    initialMappings,
  };
}
