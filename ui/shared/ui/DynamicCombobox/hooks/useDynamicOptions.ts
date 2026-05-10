// ui/shared/ui/DynamicCombobox/hooks/useDynamicOptions.ts

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { apiRequest } from '@/shared/api';
import { DynamicOptionsConfig } from '@/shared/types/schema';
import type { Step } from '@/shared/types/workflow';
import { isExpression, resolveValue } from '@/shared/lib/expression-utils';

export interface FieldOption {
  value: string;
  label: string;
  metadata?: Record<string, any>;
}

interface FieldOptionsResponse {
  options: FieldOption[];
  total: number;
  cached: boolean;
}

const optionsCache = new Map<string, { options: FieldOption[]; timestamp: number }>();
const CACHE_TTL_MS = 60000;

const lastFetchTime = new Map<string, number>();
// 750ms catches pathological loops while still feeling responsive; the 300ms debounce handles rapid typing.
const MIN_FETCH_INTERVAL_MS = 750;

export const isVariableMapping = (val: string) => /\{\{.*?\}\}/.test(val);

interface UseDynamicOptionsParams {
  credentialId?: string;
  providerId: string;
  dynamicOptions: DynamicOptionsConfig;
  formData: Record<string, any>;
  previousSteps?: Step[];
  value: string | string[];
  multiple: boolean;
}

export function useDynamicOptions({
  credentialId,
  providerId,
  dynamicOptions,
  formData,
  previousSteps = [],
  value,
  multiple,
}: UseDynamicOptionsParams) {
  const [options, setOptions] = useState<FieldOption[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dependencies = useMemo(
    () => dynamicOptions.dependsOn
      ? (Array.isArray(dynamicOptions.dependsOn)
          ? dynamicOptions.dependsOn
          : [dynamicOptions.dependsOn])
      : [],
    [dynamicOptions.dependsOn]
  );

  const expressionContext = useMemo(() => ({ previousSteps }), [previousSteps]);

  const resolvedFormData = useMemo(() => {
    const resolved: Record<string, any> = {};
    for (const [key, val] of Object.entries(formData)) {
      resolved[key] = resolveValue(val, expressionContext);
    }
    return resolved;
  }, [formData, expressionContext]);

  // Only relevant dependency values - avoids refetching on unrelated form field changes.
  const dependencyValues = dependencies.map(dep => resolvedFormData[dep.field]).join('|');

  const checkDependencies = useCallback(() => {
    if (dependencies.length === 0) return { satisfied: true, missing: [] as string[] };

    const missing: string[] = [];
    for (const dep of dependencies) {
      const depValue = resolvedFormData[dep.field];
      if (!depValue || (typeof depValue === 'string' && isExpression(depValue))) {
        missing.push(dep.field);
      }
    }

    return { satisfied: missing.length === 0, missing };
  }, [dependencies, resolvedFormData]);

  const getCacheKey = useCallback(() => {
    const depParams: Record<string, any> = {};
    for (const dep of dependencies) {
      const val = resolvedFormData[dep.field];
      if (val && typeof val === 'string' && !isExpression(val)) {
        depParams[dep.param] = val;
      } else if (val && typeof val !== 'string') {
        depParams[dep.param] = val;
      }
    }
    return `${providerId}:${credentialId}:${dynamicOptions.service}:${dynamicOptions.optionsPath}:${JSON.stringify(depParams)}`;
  }, [providerId, credentialId, dynamicOptions.service, dynamicOptions.optionsPath, dependencies, dependencyValues]); // eslint-disable-line react-hooks/exhaustive-deps -- resolvedFormData excluded; dependencyValues already captures the relevant subset to avoid rebuilding cache key on unrelated form changes

  const fetchOptions = useCallback(async (forceRefresh = false) => {
    if (!credentialId) {
      setError('No credential selected');
      return;
    }

    const { satisfied } = checkDependencies();
    if (!satisfied) {
      setOptions([]);
      setError(null);
      return;
    }

    const cacheKey = getCacheKey();

    if (!forceRefresh) {
      const cached = optionsCache.get(cacheKey);
      if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
        setOptions(cached.options);
        setError(null);
        return;
      }
    }

    const lastFetch = lastFetchTime.get(cacheKey) || 0;
    const timeSinceLastFetch = Date.now() - lastFetch;
    if (timeSinceLastFetch < MIN_FETCH_INTERVAL_MS) {
      return;
    }

    setIsLoading(true);
    setError(null);
    lastFetchTime.set(cacheKey, Date.now());

    try {
      const params = new URLSearchParams({
        credential_id: credentialId,
        service: dynamicOptions.service,
        options_path: dynamicOptions.optionsPath,
        value_field: dynamicOptions.valueField,
        label_field: dynamicOptions.labelField,
      });

      const body: Record<string, any> = {};
      for (const dep of dependencies) {
        const val = resolvedFormData[dep.field];
        if (val && typeof val === 'string' && !isExpression(val)) {
          body[dep.param] = val;
        } else if (val && typeof val !== 'string') {
          body[dep.param] = val;
        }
      }

      const response = await apiRequest<FieldOptionsResponse>(
        `/providers/${providerId}/field-options?${params.toString()}`,
        {
          method: 'POST',
          body: JSON.stringify({ parameters: body }),
        }
      );

      const fetchedOptions = response.options || [];
      optionsCache.set(cacheKey, { options: fetchedOptions, timestamp: Date.now() });

      setOptions(fetchedOptions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch options');
      setOptions([]);
    } finally {
      setIsLoading(false);
    }
  }, [credentialId, providerId, dynamicOptions, checkDependencies, dependencies, getCacheKey, dependencyValues]); // eslint-disable-line react-hooks/exhaustive-deps -- resolvedFormData excluded; dependency values are already tracked via dependencyValues to avoid refetching on unrelated form field changes

  const prevDependencyValuesRef = useRef<string | null>(null);
  const hasLoadedOnceRef = useRef(false);
  const hasResolvedInitialValueRef = useRef(false);

  const singleValue = multiple ? '' : (typeof value === 'string' ? value : '');
  const selectedValuesLength = multiple
    ? (Array.isArray(value) ? value.length : (value ? 1 : 0))
    : 0;

  // Fetch once on mount when a saved value exists - ensures the label resolves rather than showing a raw ID.
  useEffect(() => {
    if (hasResolvedInitialValueRef.current) return;

    const hasValueToResolve = multiple
      ? selectedValuesLength > 0
      : singleValue && !isVariableMapping(singleValue);

    if (hasValueToResolve && credentialId && !hasLoadedOnceRef.current) {
      fetchOptions();
      hasLoadedOnceRef.current = true;
      hasResolvedInitialValueRef.current = true;
    }
  }, [credentialId, singleValue, selectedValuesLength]); // eslint-disable-line react-hooks/exhaustive-deps -- fetchOptions and multiple excluded; runs once on mount to resolve initial saved value, refs guard against repeated execution

  // Dependency change: clear stale options; fetch deferred until dropdown opens.
  useEffect(() => {
    const prevValues = prevDependencyValuesRef.current;
    prevDependencyValuesRef.current = dependencyValues;

    if (prevValues === null || prevValues === dependencyValues) return;

    setOptions([]);
    hasLoadedOnceRef.current = false;
  }, [dependencyValues]);

  const handleLazyLoad = useCallback(() => {
    if (!hasLoadedOnceRef.current && credentialId) {
      fetchOptions();
      hasLoadedOnceRef.current = true;
    }
  }, [credentialId, fetchOptions]);

  const { satisfied: dependenciesSatisfied, missing: missingDeps } = checkDependencies();

  return {
    options,
    isLoading,
    error,
    fetchOptions,
    handleLazyLoad,
    dependenciesSatisfied,
    missingDeps,
    hasDependencies: dependencies.length > 0,
  };
}
