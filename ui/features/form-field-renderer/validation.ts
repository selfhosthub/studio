// ui/features/form-field-renderer/validation.ts

/**
 * Shared required-field validation for all form entry points. Callers map
 * their schema into `RequiredCheckEntry` items and call
 * `collectMissingRequiredFields` - do not duplicate the emptiness rules.
 */

/**
 * Returns true when `value` counts as empty for required-field validation.
 * `undefined`/`null`, blank strings, empty arrays, and empty objects are empty;
 * `0`, `false`, and non-empty containers are present.
 *
 * Native HTML5 `required` is not applied to checkbox/multiselect/tags/
 * key-value/json inputs, so relying on it alone leaves a silent gap for
 * those types. This function closes the gap.
 */
export function isRequiredValueMissing(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as object).length === 0;
  return false;
}

export interface RequiredCheckEntry {
  /** Human-readable field label surfaced in the error message. */
  label: string;
  /** Is this field marked required in its schema? */
  required: boolean;
  /** Effective current value (user-typed if present, saved/default otherwise). */
  value: unknown;
}

/**
 * Returns the list of required-field labels whose value is empty, in the
 * order supplied. Empty list means "submit is allowed".
 */
export function collectMissingRequiredFields(entries: RequiredCheckEntry[]): string[] {
  const missing: string[] = [];
  for (const entry of entries) {
    if (entry.required && isRequiredValueMissing(entry.value)) {
      missing.push(entry.label);
    }
  }
  return missing;
}

/**
 * Compiles a field's `pattern` config into a full-match RegExp.
 * Returns null for an invalid pattern so callers skip the check.
 */
export function compileFieldPattern(pattern: string): RegExp | null {
  try {
    return new RegExp(`^(?:${pattern})$`);
  } catch {
    return null;
  }
}

export interface PatternCheckEntry {
  /** Human-readable field label surfaced in the error message. */
  label: string;
  /** Optional regex the value must fully match. */
  pattern?: string;
  /** Effective current value (user-typed if present, saved/default otherwise). */
  value: unknown;
}

export interface PatternViolation {
  label: string;
  pattern: string;
}

/**
 * Returns the entries whose non-empty string value fails its pattern, in the
 * order supplied. Empty values and invalid patterns are skipped.
 */
export function collectPatternViolations(entries: PatternCheckEntry[]): PatternViolation[] {
  const violations: PatternViolation[] = [];
  for (const entry of entries) {
    if (!entry.pattern || typeof entry.value !== 'string' || entry.value === '') continue;
    const regex = compileFieldPattern(entry.pattern);
    if (regex && !regex.test(entry.value)) {
      violations.push({ label: entry.label, pattern: entry.pattern });
    }
  }
  return violations;
}
