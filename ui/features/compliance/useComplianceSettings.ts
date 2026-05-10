// ui/features/compliance/useComplianceSettings.ts

/**
 * useComplianceSettings Hook
 *
 * Fetches ROSCA/compliance settings from the public API.
 * These settings control subscription disclosure text shown to users
 * before they commit to a recurring subscription.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { getPublicComplianceSettings } from '@/shared/api';

export interface ComplianceSettings {
  rosca_enabled: boolean;
  trial_disclosure: string;
  recurring_disclosure: string;
  one_time_disclosure: string;
  cancellation_instructions: string;
  consent_checkbox_text: string;
  registration_disclosure: string;
}

// Default values matching backend defaults
const defaultSettings: ComplianceSettings = {
  rosca_enabled: false,
  trial_disclosure:
    'After your {trial_days}-day free trial ends on {trial_end_date}, ' +
    'you will be automatically charged {price} every {interval} until you cancel.',
  recurring_disclosure:
    'You will be charged {price} today and automatically every {interval} until you cancel.',
  one_time_disclosure: 'This is a one-time payment of {price}. No recurring charges.',
  cancellation_instructions:
    'You can cancel anytime from your account Settings → Billing page. ' +
    'Your access continues until the end of your billing period.',
  consent_checkbox_text:
    'I understand this is a recurring subscription and I will be charged ' +
    '{price} every {interval} until I cancel.',
  registration_disclosure:
    'By creating an account with the {plan_name} plan, you agree to be charged ' +
    '{price}/{interval} after any applicable trial period. ' +
    'You can cancel anytime from your account settings.',
};

interface UseComplianceSettingsResult {
  settings: ComplianceSettings;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

/**
 * Format a disclosure template by replacing placeholders with actual values
 */
export function formatDisclosure(
  template: string,
  values: {
    trial_days?: number;
    trial_end_date?: string;
    price?: string;
    interval?: string;
    plan_name?: string;
  }
): string {
  let result = template;

  if (values.trial_days !== undefined) {
    result = result.replace(/{trial_days}/g, String(values.trial_days));
  }
  if (values.trial_end_date) {
    result = result.replace(/{trial_end_date}/g, values.trial_end_date);
  }
  if (values.price) {
    result = result.replace(/{price}/g, values.price);
  }
  if (values.interval) {
    result = result.replace(/{interval}/g, values.interval);
  }
  if (values.plan_name) {
    result = result.replace(/{plan_name}/g, values.plan_name);
  }

  return result;
}

export function useComplianceSettings(): UseComplianceSettingsResult {
  const [settings, setSettings] = useState<ComplianceSettings>(defaultSettings);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    try {
      const data = await getPublicComplianceSettings();
      setSettings(data);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch compliance settings:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch compliance settings');
      // Use defaults on error
      setSettings(defaultSettings);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  return {
    settings,
    isLoading,
    error,
    refresh: fetchSettings,
  };
}
