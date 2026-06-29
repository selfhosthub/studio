// ui/shared/lib/schedule-utils.ts

export type RecurrenceChoice = 'none' | 'daily' | 'weekly' | 'monthly' | 'custom';

/** Maps a friendly recurrence choice to an RRULE string (null = does not repeat). */
export function recurrenceToRrule(choice: RecurrenceChoice, customRrule = ''): string | null {
  switch (choice) {
    case 'daily':
      return 'FREQ=DAILY';
    case 'weekly':
      return 'FREQ=WEEKLY';
    case 'monthly':
      return 'FREQ=MONTHLY';
    case 'custom':
      return customRrule.trim() || null;
    case 'none':
    default:
      return null;
  }
}

/** Maps a stored RRULE string back to a friendly recurrence choice. */
export function rruleToRecurrence(rrule: string | null | undefined): RecurrenceChoice {
  if (!rrule || !rrule.trim()) return 'none';
  const normalized = rrule.trim().toUpperCase();
  if (normalized === 'FREQ=DAILY') return 'daily';
  if (normalized === 'FREQ=WEEKLY') return 'weekly';
  if (normalized === 'FREQ=MONTHLY') return 'monthly';
  return 'custom';
}

/** Browser timezone, falling back to UTC. */
export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/** Minimal IANA timezone fallback when Intl.supportedValuesOf is unavailable. */
const FALLBACK_TIMEZONES = [
  'UTC',
  'America/Los_Angeles',
  'America/Denver',
  'America/Chicago',
  'America/New_York',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Moscow',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Australia/Sydney',
];

/**
 * Sorted list of IANA timezone names for a dropdown.
 * Uses the browser-supported list when available, otherwise a small fallback.
 * `ensure` is always included (e.g. a stored value not in the supported list).
 */
export function getTimezoneOptions(ensure?: string | null): string[] {
  let zones: string[];
  try {
    const supported = (Intl as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf;
    zones = supported ? supported('timeZone') : [...FALLBACK_TIMEZONES];
  } catch {
    zones = [...FALLBACK_TIMEZONES];
  }
  if (!zones.includes('UTC')) zones = ['UTC', ...zones];
  if (ensure && !zones.includes(ensure)) zones = [...zones, ensure].sort();
  return zones;
}
