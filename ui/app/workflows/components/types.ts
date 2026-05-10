// ui/app/workflows/components/types.ts

// Shared types used by WorkflowStepConfig hooks
//
// These types mirror the parameter schema structures returned by the provider API.
// Fields use `any` where the original component did, since values flow from untyped
// API responses and are consumed by MappableParameterField which also uses `any`.

export interface ParamConfig {
  type?: string;
  title?: string;
  description?: string;
  default?: any;
  enum?: string[];
  enumNames?: string[];
  required?: boolean;
  minimum?: number;
  maximum?: number;
  format?: string;
  dynamicOptions?: any;
  ui?: {
    section?: string;
    group?: string;
    order?: number;
    hidden?: boolean;
    show_when?: Record<string, any>;
    widget?: string;
    placeholder?: string;
    rows?: number;
    inlineWith?: string;
    hint?: string;
    visibleWhen?: {
      field: string;
      condition: string;
      value?: any;
    };
  };
}

export interface SectionConfig {
  title: string;
  description?: string;
  collapsed?: boolean;
  order?: number;
}

export interface ParameterUiState {
  expandedGroups?: Record<string, boolean>;
  expandedItems?: Record<string, boolean>;
  collapsedSections?: Record<string, boolean>;
}
