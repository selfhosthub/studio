// ui/features/form-field-renderer/FormFieldRenderer.tsx

'use client';

import React from 'react';
import type { FormFieldConfig, FormFieldType } from '@/entities/workflow';
import { TextField } from './fields/TextField';
import { TextareaField } from './fields/TextareaField';
import { NumberField } from './fields/NumberField';
import { SelectField } from './fields/SelectField';
import { MultiselectField } from './fields/MultiselectField';
import { CheckboxField } from './fields/CheckboxField';
import { FileField } from './fields/FileField';
import { DateField } from './fields/DateField';
import { DatetimeField } from './fields/DatetimeField';
import { JsonField } from './fields/JsonField';
import { TagsField } from './fields/TagsField';
import { KeyValueField } from './fields/KeyValueField';

export interface FormFieldRendererProps {
  /** Canonical (camelCase) config. Entry points normalize before calling. */
  config: FormFieldConfig;
  /** Current field value. Shape varies by fieldType. */
  value: unknown;
  /** Emits the new value. Entry points adapt to their own keying model. */
  onChange: (next: unknown) => void;
  /** Optional validation error; subcomponents apply error styling when set. */
  error?: string;
  /** Focus this field on mount - used by the first field in PreRunForm. */
  autoFocus?: boolean;
  /**
   * Stable param key for widgets that need one (TagsInput, MultiselectInput
   * use it as a state discriminator). Optional - subcomponents fall back to
   * an empty string when not supplied.
   */
  paramKey?: string;
}

/**
 * Canonical form-field renderer - single switch over `FormFieldType`; every union
 * member routes to a dedicated subcomponent. No caller should switch on `fieldType`
 * directly. A coverage test asserts every `FormFieldType` member renders a
 * non-fallback subcomponent, so adding a type without a subcomponent fails CI.
 */
export function FormFieldRenderer({
  config,
  value,
  onChange,
  error,
  autoFocus,
  paramKey,
}: FormFieldRendererProps) {
  const fieldType = config.fieldType as FormFieldType | undefined;

  switch (fieldType) {
    case 'textarea':
      return <TextareaField config={config} value={value} onChange={onChange} error={error} autoFocus={autoFocus} />;
    case 'number':
      return <NumberField config={config} value={value} onChange={onChange} error={error} autoFocus={autoFocus} />;
    case 'select':
      return <SelectField config={config} value={value} onChange={onChange} error={error} />;
    case 'multiselect':
      return <MultiselectField config={config} value={value} onChange={onChange} paramKey={paramKey} />;
    case 'checkbox':
      return <CheckboxField config={config} value={value} onChange={onChange} />;
    case 'file':
      return <FileField config={config} value={value} onChange={onChange} error={error} />;
    case 'date':
      return <DateField config={config} value={value} onChange={onChange} error={error} />;
    case 'datetime':
      return <DatetimeField config={config} value={value} onChange={onChange} error={error} />;
    case 'json':
      return <JsonField config={config} value={value} onChange={onChange} error={error} />;
    case 'tags':
      return <TagsField config={config} value={value} onChange={onChange} paramKey={paramKey} />;
    case 'key-value':
      return <KeyValueField config={config} value={value} onChange={onChange} />;
    case 'text':
    default:
      return <TextField config={config} value={value} onChange={onChange} error={error} autoFocus={autoFocus} />;
  }
}
