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

/** Wall-clock parts of an instant in an IANA timezone. */
function zonedParts(epochMs: number, timeZone: string): number[] {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(new Date(epochMs));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  return [get('year'), get('month'), get('day'), get('hour'), get('minute'), get('second')];
}

/** Offset in ms of a timezone from UTC at an instant. */
function zoneOffsetMs(epochMs: number, timeZone: string): number {
  const [y, mo, d, h, mi, s] = zonedParts(epochMs, timeZone);
  return Date.UTC(y, mo - 1, d, h, mi, s) - Math.floor(epochMs / 1000) * 1000;
}

/** Reads a datetime-local value as wall-clock time in timeZone and returns its UTC ISO string. */
export function zonedInputToUtcIso(local: string, timeZone: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(local);
  if (!m) return null;
  const asUtc = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  let result = asUtc - zoneOffsetMs(asUtc, timeZone);
  const corrected = asUtc - zoneOffsetMs(result, timeZone);
  if (corrected !== result) result = corrected;
  return new Date(result).toISOString();
}

/** Renders a stored instant as a datetime-local value in timeZone. */
export function utcIsoToZonedInput(iso: string | null, timeZone: string): string {
  if (!iso) return '';
  const epoch = new Date(iso).getTime();
  if (isNaN(epoch)) return '';
  const [y, mo, d, h, mi] = zonedParts(epoch, timeZone);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${y}-${pad(mo)}-${pad(d)}T${pad(h)}:${pad(mi)}`;
}
