// ui/features/step-config/sections/BaseServiceSection.tsx

'use client';

import React, { useEffect, useState, useMemo, KeyboardEvent } from 'react';
import { useSharedStepConfig } from '../context/SharedStepConfigContext';
import { ServiceDefinition } from '@/entities/provider';
import { ChevronDown, ChevronRight, X, HelpCircle } from 'lucide-react';
import { ResolutionPicker } from '../MappableParameterField/components/ResolutionPicker';
import { UserFilePicker } from '@/features/files';

interface BaseServiceSectionProps {
  title?: string;
}

interface ParamConfig {
  type?: string;
  format?: string;
  title?: string;
  description?: string;
  default?: any;
  enum?: string[];
  enumNames?: string[];
  required?: boolean;
  minimum?: number;
  maximum?: number;
  items?: any;
  properties?: Record<string, ParamConfig>;
  additionalProperties?: boolean;
  ui?: {
    section?: string;
    group?: string;
    order?: number;
    hidden?: boolean;
    show_when?: Record<string, any>;
    widget?: string;
    placeholder?: string;
    rows?: number;
    hints?: string[];
  };
}

interface SectionConfig {
  title: string;
  description?: string;
  collapsed?: boolean;
  order?: number;
}

interface SectionedParams {
  [sectionName: string]: { key: string; config: ParamConfig }[];
}

export default function BaseServiceSection({ title = 'Service' }: BaseServiceSectionProps) {
  const {
    providerId,
    serviceId,
    setServiceId,
    services,
    parameters,
    setParameters,
    paramSchema,
    loading,
    service
  } = useSharedStepConfig();

  // Track collapsed state for sections
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  // Get section config from service ui_hints
  const sectionConfigs = useMemo((): Record<string, SectionConfig> => {
    const uiHints = (service as any)?.client_metadata?.ui_hints?.sections ||
                    (service as any)?.ui_hints?.sections || {};
    return uiHints;
  }, [service]);

  // Initialize collapsed state from section configs
  useEffect(() => {
    const initialCollapsed: Record<string, boolean> = {};
    Object.entries(sectionConfigs).forEach(([name, config]) => {
      if (config.collapsed !== undefined) {
        initialCollapsed[name] = config.collapsed;
      }
    });
    setCollapsedSections(prev => ({ ...initialCollapsed, ...prev }));
  }, [sectionConfigs]);


  // Check if a parameter should be visible based on show_when conditions
  const isParamVisible = (config: ParamConfig): boolean => {
    if (!config.ui?.show_when) return true;

    for (const [field, expectedValue] of Object.entries(config.ui.show_when)) {
      const actualValue = parameters[field];
      // show_when can be an array of acceptable values or a single value
      if (Array.isArray(expectedValue)) {
        if (!expectedValue.includes(actualValue)) {
          return false;
        }
      } else if (actualValue !== expectedValue) {
        return false;
      }
    }
    return true;
  };

  // Group parameters by section
  const sectionedParams = useMemo((): SectionedParams => {
    if (!paramSchema || Object.keys(paramSchema).length === 0) {
      return {};
    }

    const sections: SectionedParams = {};

    // Sort entries by ui.order if available
    const sortedEntries = Object.entries(paramSchema).sort((a, b) => {
      const orderA = (a[1] as ParamConfig)?.ui?.order ?? 999;
      const orderB = (b[1] as ParamConfig)?.ui?.order ?? 999;
      return orderA - orderB;
    });

    for (const [paramKey, paramConfig] of sortedEntries) {
      const config = paramConfig as ParamConfig;
      const section = config.ui?.section || 'default';

      if (config.ui?.hidden) continue;

      if (!sections[section]) {
        sections[section] = [];
      }
      sections[section].push({ key: paramKey, config });
    }

    return sections;
  }, [paramSchema]);

  // Get sorted section names
  const sortedSectionNames = useMemo(() => {
    const names = Object.keys(sectionedParams);
    return names.sort((a, b) => {
      const orderA = sectionConfigs[a]?.order ?? 999;
      const orderB = sectionConfigs[b]?.order ?? 999;
      return orderA - orderB;
    });
  }, [sectionedParams, sectionConfigs]);

  // Function to update a single parameter
  const updateServiceParameter = (key: string, value: any) => {
    setParameters({
      ...parameters,
      [key]: value
    });
  };

  const toggleSection = (sectionName: string) => {
    setCollapsedSections(prev => ({
      ...prev,
      [sectionName]: !prev[sectionName]
    }));
  };

  // Track which hints modal is open
  const [openHintsKey, setOpenHintsKey] = useState<string | null>(null);

  // Tags/Chips input component for array fields
  const TagsInput = ({
    value,
    onChange,
    placeholder,
    itemType = 'string',
    presets = []
  }: {
    value: any[];
    onChange: (newValue: any[]) => void;
    placeholder?: string;
    itemType?: 'string' | 'integer' | 'number';
    presets?: (string | number)[];
  }) => {
    const [inputValue, setInputValue] = useState('');

    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' || e.key === ',' || e.key === 'Tab') {
        e.preventDefault();
        addTag();
      } else if (e.key === 'Backspace' && inputValue === '' && value.length > 0) {
        // Remove last tag on backspace when input is empty
        onChange(value.slice(0, -1));
      }
    };

    const addTag = () => {
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
        onChange([...value, newValue]);
      }
      setInputValue('');
    };

    const removeTag = (index: number) => {
      const newTags = [...value];
      newTags.splice(index, 1);
      onChange(newTags);
    };

    const addPreset = (preset: string | number) => {
      if (!value.includes(preset)) {
        onChange([...value, preset]);
      }
    };

    // Filter out presets that are already in value
    const availablePresets = presets.filter(p => !value.includes(p));

    return (
      <div className="space-y-2">
        {/* Tags display + input container */}
        <div className="min-h-[42px] w-full px-2 py-1.5 border border-primary rounded-md shadow-sm focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-info flex flex-wrap gap-1.5 items-center">
          {value.map((tag, index) => (
            <span
              key={`${tag}-${index}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-info-subtle text-info text-sm rounded-md"
            >
              {String(tag)}
              <button
                type="button"
                onClick={() => removeTag(index)}
                className="hover:text-info"
              >
                <X size={12} />
              </button>
            </span>
          ))}
          <input
            type={itemType === 'string' ? 'text' : 'number'}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={addTag}
            className="flex-1 min-w-[80px] bg-transparent border-none outline-none text-sm py-0.5"
            placeholder={value.length === 0 ? placeholder : 'Type and press Enter'}
          />
        </div>

        {/* Preset suggestions */}
        {availablePresets.length > 0 && (
          <div className="flex flex-wrap gap-1">
            <span className="text-xs text-secondary mr-1">Quick add:</span>
            {availablePresets.slice(0, 6).map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => addPreset(preset)}
                className="px-1.5 py-0.5 text-xs bg-card text-secondary rounded hover:bg-input"
              >
                +{String(preset)}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  };

  // Render a single parameter field
  const renderParamField = (paramKey: string, paramConfig: ParamConfig) => {
    // Check visibility conditions
    if (!isParamVisible(paramConfig)) {
      return null;
    }

    const paramValue = parameters[paramKey] !== undefined
      ? parameters[paramKey]
      : paramConfig.default;

    const displayLabel = paramConfig.title || paramKey;
    const enumNames = paramConfig.enumNames || paramConfig.enum;
    const widget = paramConfig.ui?.widget;
    const placeholder = paramConfig.ui?.placeholder;
    const rows = paramConfig.ui?.rows || 3;
    const hints = paramConfig.ui?.hints;

    return (
      <div key={paramKey} className="border border-primary rounded-md p-4 relative">
        <div className="flex items-start justify-between mb-1">
          <label
            htmlFor={`param-${paramKey}`}
            className="block text-sm font-medium"
          >
            {displayLabel}{paramConfig.required ? '*' : ''}
          </label>
          {hints && hints.length > 0 && (
            <button
              type="button"
              onClick={() => setOpenHintsKey(openHintsKey === paramKey ? null : paramKey)}
              className="p-0.5 text-muted hover:text-info transition-colors"
              title="Show hints"
            >
              <HelpCircle size={16} />
            </button>
          )}
        </div>

        {paramConfig.description && (
          <p className="text-xs text-secondary mb-2">
            {paramConfig.description}
          </p>
        )}

        {/* Hints popover */}
        {hints && openHintsKey === paramKey && (
          <div className="absolute right-0 top-8 z-10 w-80 p-3 bg-card border border-primary rounded-lg shadow-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-secondary">Usage Hints</span>
              <button
                type="button"
                onClick={() => setOpenHintsKey(null)}
                className="text-muted hover:text-secondary"
              >
                <X size={14} />
              </button>
            </div>
            <ul className="text-xs text-secondary space-y-1.5">
              {hints.map((hint, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-info mt-0.5">•</span>
                  <span>{hint}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* URI file picker */}
        {paramConfig.type === 'string' && paramConfig.format === 'uri' && (() => {
          const fieldNameLower = paramKey.toLowerCase();
          const titleLower = (paramConfig.title || '').toLowerCase();
          const mediaTypeFilter: 'image' | 'video' | 'audio' | 'all' =
            fieldNameLower.includes('image') || titleLower.includes('image') ? 'image' :
            fieldNameLower.includes('video') || titleLower.includes('video') ? 'video' :
            fieldNameLower.includes('audio') || titleLower.includes('audio') ? 'audio' : 'all';
          return (
            <UserFilePicker
              value={paramValue ?? ''}
              onChange={(url) => updateServiceParameter(paramKey, url)}
              mediaTypeFilter={mediaTypeFilter}
              placeholder={placeholder || paramConfig.description || 'Enter URL or select file...'}
            />
          );
        })()}

        {/* String input (text, password, or textarea) */}
        {paramConfig.type === 'string' && !paramConfig.enum && paramConfig.format !== 'uri' && (
          widget === 'textarea' ? (
            <textarea
              id={`param-${paramKey}`}
              value={paramValue || ''}
              onChange={(e) => updateServiceParameter(paramKey, e.target.value)}
              rows={rows}
              className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
              placeholder={placeholder || paramConfig.description || `Enter ${displayLabel}`}
            />
          ) : (
            <input
              id={`param-${paramKey}`}
              type="text"
              value={paramValue || ''}
              onChange={(e) => updateServiceParameter(paramKey, e.target.value)}
              className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
              placeholder={placeholder || paramConfig.description || `Enter ${displayLabel}`}
            />
          )
        )}

        {/* Resolution picker widget */}
        {widget === 'resolution-picker' && (
          <ResolutionPicker
            width={paramValue ?? paramConfig.default ?? 1920}
            height={parameters.height ?? 1080}
            onWidthChange={(w) => updateServiceParameter(paramKey, w)}
            onHeightChange={(h) => updateServiceParameter('height', h)}
            minValue={paramConfig.minimum}
            maxValue={paramConfig.maximum}
          />
        )}

        {/* Number input */}
        {(paramConfig.type === 'number' || paramConfig.type === 'integer') && widget !== 'resolution-picker' && (
          <input
            id={`param-${paramKey}`}
            type="number"
            value={paramValue ?? ''}
            onChange={(e) => updateServiceParameter(paramKey, e.target.value ? Number(e.target.value) : undefined)}
            min={paramConfig.minimum}
            max={paramConfig.maximum}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
            placeholder={placeholder || paramConfig.description || `Enter ${displayLabel}`}
          />
        )}

        {/* Boolean checkbox */}
        {paramConfig.type === 'boolean' && (
          <div className="flex items-center">
            <input
              id={`param-${paramKey}`}
              type="checkbox"
              checked={!!paramValue}
              onChange={(e) => updateServiceParameter(paramKey, e.target.checked)}
              className="h-4 w-4 text-info focus:ring-blue-500 border-primary rounded"
            />
            <label htmlFor={`param-${paramKey}`} className="ml-2 block text-sm text-secondary">
              {paramConfig.description || displayLabel}
            </label>
          </div>
        )}

        {/* Enum select */}
        {paramConfig.type === 'string' && paramConfig.enum && (
          <select
            id={`param-${paramKey}`}
            value={paramValue || ''}
            onChange={(e) => updateServiceParameter(paramKey, e.target.value)}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
          >
            {/* Only show empty option if no default - required fields prompt, optional fields are blank */}
            {paramConfig.default === undefined && (
              <option value="">{paramConfig.required ? `Select ${displayLabel}` : ''}</option>
            )}
            {paramConfig.enum.map((option: string, idx: number) => (
              <option key={option} value={option}>
                {enumNames?.[idx] || option}
              </option>
            ))}
          </select>
        )}

        {/* Object type - JSON editor */}
        {paramConfig.type === 'object' && (
          <textarea
            id={`param-${paramKey}`}
            value={typeof paramValue === 'object' ? JSON.stringify(paramValue, null, 2) : (paramValue || '')}
            onChange={(e) => {
              try {
                const parsed = JSON.parse(e.target.value);
                updateServiceParameter(paramKey, parsed);
              } catch {
                // Allow typing invalid JSON temporarily
                updateServiceParameter(paramKey, e.target.value);
              }
            }}
            rows={rows}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info font-mono text-sm"
            placeholder={placeholder || '{ }'}
          />
        )}

        {/* Array type with tags widget - chips input with presets */}
        {paramConfig.type === 'array' && widget === 'tags' && (
          <TagsInput
            value={Array.isArray(paramValue) ? paramValue : (paramConfig.default || [])}
            onChange={(newValue) => updateServiceParameter(paramKey, newValue)}
            placeholder={placeholder || `Type and press Enter to add`}
            itemType={paramConfig.items?.type || 'string'}
            presets={
              // Preset common status codes for specific fields
              paramKey === 'success_codes' ? [200, 201, 202, 204] :
              paramKey === 'fail_codes' ? [400, 401, 403, 404, 500, 502, 503] :
              paramKey === 'fail_values' ? ['error', 'failed', 'timeout'] :
              []
            }
          />
        )}

        {/* Array type - JSON editor fallback */}
        {paramConfig.type === 'array' && widget !== 'tags' && (
          <textarea
            id={`param-${paramKey}`}
            value={Array.isArray(paramValue) ? JSON.stringify(paramValue, null, 2) : (paramValue || '[]')}
            onChange={(e) => {
              try {
                const parsed = JSON.parse(e.target.value);
                updateServiceParameter(paramKey, parsed);
              } catch {
                // Allow typing invalid JSON temporarily
                updateServiceParameter(paramKey, e.target.value);
              }
            }}
            rows={Math.max(rows, 6)}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info font-mono text-sm"
            placeholder={placeholder || '[ ]'}
          />
        )}
      </div>
    );
  };

  // Render a section with its parameters
  const renderSection = (sectionName: string, params: { key: string; config: ParamConfig }[]) => {
    const sectionConfig = sectionConfigs[sectionName];
    const isCollapsed = collapsedSections[sectionName] ?? (sectionConfig?.collapsed ?? false);
    const sectionTitle = sectionConfig?.title || sectionName;

    // Filter params to only visible ones
    const visibleParams = params.filter(({ config }) => isParamVisible(config));
    if (visibleParams.length === 0) return null;

    // For 'basic' or 'default' section, render without collapsible header
    if (sectionName === 'basic' || sectionName === 'default') {
      return (
        <div key={sectionName} className="space-y-4">
          {visibleParams.map(({ key, config }) => renderParamField(key, config))}
        </div>
      );
    }

    // For named sections, render as collapsible
    return (
      <div key={sectionName} className="border border-primary rounded-md">
        <button
          type="button"
          onClick={() => toggleSection(sectionName)}
          className="w-full flex items-center justify-between px-4 py-3 text-left bg-surface hover:bg-card rounded-t-md"
        >
          <div>
            <span className="text-md font-medium">{sectionTitle}</span>
            {sectionConfig?.description && (
              <p className="text-xs text-secondary mt-0.5">{sectionConfig.description}</p>
            )}
          </div>
          {isCollapsed ? (
            <ChevronRight className="h-5 w-5 text-secondary flex-shrink-0" />
          ) : (
            <ChevronDown className="h-5 w-5 text-secondary flex-shrink-0" />
          )}
        </button>

        {!isCollapsed && (
          <div className="p-4 space-y-4">
            {visibleParams.map(({ key, config }) => renderParamField(key, config))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      <h3 className="text-lg font-medium mb-4">{title}</h3>

      <div className="space-y-6">
        <div>
          <label htmlFor="service-select" className="block text-sm font-medium mb-1">
            Select Service
          </label>
          <select
            id="service-select"
            value={serviceId}
            onChange={(e) => setServiceId(e.target.value)}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
            disabled={!providerId || loading}
          >
            <option value="">Select a service</option>
            {services.map((svc: ServiceDefinition) => (
              <option key={svc.id} value={svc.service_id}>
                {svc.display_name || svc.name}
              </option>
            ))}
          </select>

          {loading && (
            <div className="mt-2 text-sm text-secondary">
              Loading services...
            </div>
          )}
        </div>

        {/* Render all sections in order */}
        {serviceId && sortedSectionNames.map(sectionName => (
          renderSection(sectionName, sectionedParams[sectionName])
        ))}

        {/* Special handling for body field in HTTP services */}
        {serviceId && (service as any)?.service_type === 'HTTP' && (
          <div className="mt-6">
            <div className="border border-primary rounded-md p-4">
              <label htmlFor="param-body" className="block text-sm font-medium mb-1">
                Body
              </label>
              <p className="text-xs text-secondary mb-2">
                Request body for HTTP request
              </p>
              <textarea
                id="param-body"
                value={parameters.body || ''}
                onChange={(e) => updateServiceParameter('body', e.target.value)}
                rows={5}
                className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
                placeholder="Enter request body (JSON, XML, form data, etc.)"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
