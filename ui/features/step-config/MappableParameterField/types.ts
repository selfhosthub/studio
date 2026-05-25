// ui/features/step-config/MappableParameterField/types.ts

// Types for MappableParameterField and related components

import { Step } from '@/entities/workflow';

// Extended schema interface to support JSON Schema features
export interface PropertySchema {
  type?: string;
  title?: string;
  description?: string;
  enum?: (string | number)[];
  enumNames?: string[];
  default?: any;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  format?: string;
  items?: PropertySchema & { properties?: Record<string, PropertySchema>; required?: string[]; ui_groups?: UIGroupConfig };
  properties?: Record<string, PropertySchema>;
  required?: string[];
  /** If true, this array parameter can be iterated over (each element processed separately) */
  iterable?: boolean;
  /** If true, array items can be reordered with up/down buttons */
  reorderable?: boolean;
  ui?: {
    show_when?: Record<string, any>;
    widget?: string;
    order?: number;
    section?: string;
    group?: string;  // Sub-section group within array items
    placeholder?: string;
    rows?: number;  // Textarea row count (falls back to size default)
    coming_soon?: boolean;  // Mark field as not yet implemented
    prompt?: boolean;  // Allow prompt mapping for this parameter
    /** Configuration for record-editor widget */
    schemaConfig?: {
      dependsOn?: string[];
      schemaParams?: Record<string, string>;
      isUpdate?: boolean;
    };
    /** Placeholder for the key column of key-value widget. */
    keyPlaceholder?: string;
    /** Placeholder for the value column of key-value widget. */
    valuePlaceholder?: string;
    /** Button label for adding a new pair in the key-value widget. */
    addLabel?: string;
  };
  /** Dynamic options configuration for fetching dropdown options from provider API */
  dynamicOptions?: {
    service: string;
    optionsPath: string;
    valueField: string;
    labelField: string;
    dependsOn?: {
      field: string;
      param: string;
    };
  };
}

// Configuration for UI groups (sub-sections within arrays)
export interface UIGroupConfig {
  [groupId: string]: {
    title: string;
    order: number;
    collapsed?: boolean;
    show_when?: Record<string, any>;  // Group-level visibility
  };
}

/** All supported field mapping modes for step parameters */
export type FieldMode = 'static' | 'mapped' | 'form' | 'prompt';

export interface InputMapping {
  mappingType?: FieldMode;
  stepId?: string;
  outputField?: string;
  staticValue?: string;
  loop?: boolean;
  promptId?: string;
  promptSlug?: string;
  variableValues?: Record<string, string>;
}

// UI state that can be persisted (expanded groups, collapsed sections, etc.)
export interface UIState {
  expandedGroups?: Record<string, boolean>;  // "paramKey:itemIndex:groupId" -> expanded
  expandedItems?: Record<string, boolean>;   // "paramKey:itemIndex" -> expanded
}

// Props for the NestedArrayField component
export interface NestedArrayFieldProps {
  fieldKey: string;
  parentKey: string;
  parentItemIndex: number;  // Index of parent item in parent array (for unique key generation)
  schema: PropertySchema;
  value: any[];
  onChange: (value: any[]) => void;
  uiState?: UIState;
  onUiStateChange?: (uiState: UIState) => void;
  renderItemField: (
    fieldKey: string,
    fieldSchema: PropertySchema,
    fieldValue: any,
    itemIndex: number,
    itemData: Record<string, any>,
    onFieldChange: (key: string, value: any) => void,
    itemSchemaForDefaults?: PropertySchema,
    keyPrefix?: string  // Prefix for unique key generation in nested contexts
  ) => React.ReactNode;
}

// Props for TagsInput component
export interface TagsInputProps {
  value: (string | number)[];
  itemType: string;
  placeholder: string;
  paramKey: string;
  onChange: (key: string, value: (string | number)[]) => void;
}

// Props for MultiselectInput component
export interface MultiselectInputProps {
  value: any;
  schema: PropertySchema;
  paramKey: string;
  onValueChange: (key: string, value: any) => void;
}

// Props for ColorPickerModal component
export interface ColorPickerModalProps {
  value: string;
  onChange: (value: string) => void;
  /** Color to show in swatch when value is empty (inherited default) */
  placeholderColor?: string;
}

// Props for MappableParameterField
export interface MappableParameterFieldProps {
  paramKey: string;
  schema: PropertySchema;
  value: any;
  mapping: InputMapping | undefined;
  previousSteps: Step[];
  required?: boolean;
  onValueChange: (key: string, value: any) => void;
  onMappingChange: (key: string, mapping: InputMapping | null) => void;
  // Optional: persisted UI state (for remembering expanded groups/items)
  uiState?: UIState;
  onUiStateChange?: (uiState: UIState) => void;
  // Iteration support
  iterationConfig?: Step['iteration_config'];
  onIterationChange?: (config: Step['iteration_config']) => void;
  // Dynamic options support
  providerId?: string;
  credentialId?: string;
  /** All current field values for this step (used for dependency resolution in dynamic options) */
  allFieldValues?: Record<string, any>;
  /** Optional example value to show as placeholder hint (e.g., "e.g. appXXXXXXXXXXXXXX") */
  exampleValue?: any;
  /** All input mappings from parent (needed to detect array field form mappings) */
  allInputMappings?: Record<string, InputMapping>;
  /** Called when array items are reordered so parent can swap mapping keys */
  onReorderMappings?: (paramKey: string, fromIndex: number, toIndex: number) => void;
  /** Called when an array item is removed so parent can clean up and shift mapping keys */
  onRemoveItemMappings?: (paramKey: string, removedIndex: number, arrayLength: number) => void;
  /** Instance form fields available for mapping (workflow-level runtime inputs) */
  instanceFormFields?: Record<string, { description?: string; type?: string; _from_form?: boolean; _owning_step_ids?: string[]; _owning_step_name?: string }>;
  /** Current step ID (to exclude own fields from instance form mapping) */
  currentStepId?: string;
}
