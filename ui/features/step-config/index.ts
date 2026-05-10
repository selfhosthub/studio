// ui/features/step-config/index.ts

// Re-export all shared components and hooks
// Explicit exports from context (no export * for dev performance)
export {
  SharedStepConfigContext,
  SharedStepConfigProvider,
  useSharedStepConfig
} from './context/SharedStepConfigContext';
export { default as BaseStepConfig } from './BaseStepConfig';

// Base sections
export { default as BaseGeneralSection } from './sections/BaseGeneralSection';
export { default as BaseProviderSection } from './sections/BaseProviderSection';
export { default as BaseServiceSection } from './sections/BaseServiceSection';
export { default as BaseInputMappingsSection } from './sections/BaseInputMappingsSection';
export { default as BaseOutputFieldsSection } from './sections/BaseOutputFieldsSection';

// UI components
export { default as BaseMappingItem } from './ui/input-mapping/BaseMappingItem';
export { default as BaseMappingList } from './ui/input-mapping/BaseMappingList';
export { default as BaseOutputFieldItem } from './ui/output-fields/BaseOutputFieldItem';
export { default as BaseOutputFieldList } from './ui/output-fields/BaseOutputFieldList';