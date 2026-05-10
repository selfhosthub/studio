// ui/features/step-config/register-builtin-widgets.ts

/**
 * Builtin Array Widget Registration
 *
 * Registers all built-in array widgets with the registry.
 * Import this file early in app initialization to make widgets available.
 */

import { registerArrayWidget } from '@/shared/lib/array-widget-registry';

// Import built-in widget components
import { TagsInput } from './MappableParameterField/components/TagsInput';
import { MultiselectInput } from './MappableParameterField/components/MultiselectInput';
import { RecordEditor } from '@/features/records';
import DynamicCombobox from '@/shared/ui/DynamicCombobox';

/**
 * Register all built-in array widgets.
 * Called automatically when this module is imported.
 */
export function registerBuiltinWidgets(): void {
  // Tags widget - simple string/number array input with presets
  registerArrayWidget('tags', TagsInput);

  // Multiselect widget - enum array with reordering, favorites, search
  registerArrayWidget('multiselect', MultiselectInput);

  // Record editor widget - dynamic form builder for complex objects
  registerArrayWidget('record-editor', RecordEditor);

  // Dynamic combobox widget - fetches options from provider API
  // Note: This is registered but used via schema.dynamicOptions check, not widget name
  registerArrayWidget('dynamic-combobox', DynamicCombobox);
}

// Auto-register on module import
registerBuiltinWidgets();
