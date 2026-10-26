// ui/shared/hooks/useListPref.ts

'use client';

import { useEffect, useState, type Dispatch, type SetStateAction } from 'react';
import { listPrefKey, type ListPrefPage } from '@/shared/lib/constants';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';

export type ListPrefGuard<T> = (value: unknown) => value is T;

/** Accepts any string. */
export const isString: ListPrefGuard<string> = (value): value is string => typeof value === 'string';

/** Accepts a page size offered by the Show select. */
export const isPageSize: ListPrefGuard<number> = (value): value is number =>
  typeof value === 'number' && PAGE_SIZE_OPTIONS.includes(value);

/** Accepts one of the listed string values. */
export function oneOf<T extends string>(values: readonly T[]): ListPrefGuard<T> {
  return (value): value is T => typeof value === 'string' && (values as readonly string[]).includes(value);
}

/** Reads a stored list preference, or the fallback when it is absent, invalid or unreadable. */
export function readListPref<T>(key: string, fallback: T, guard: ListPrefGuard<T>): T {
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return fallback;
    const parsed: unknown = JSON.parse(raw);
    return guard(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

/**
 * useState for one list-page preference, kept in localStorage under
 * shs:list:<page>:<field>. A stored value the guard rejects, or storage that
 * throws, yields the default. The key is removed while the value equals the default.
 * Without a page the value lives in memory only.
 */
export function useListPref<T>(
  page: ListPrefPage | undefined,
  field: string,
  defaultValue: T,
  guard: ListPrefGuard<T>,
): [T, Dispatch<SetStateAction<T>>] {
  const key = page ? listPrefKey(page, field) : null;
  const [value, setValue] = useState<T>(() => (key ? readListPref(key, defaultValue, guard) : defaultValue));

  useEffect(() => {
    if (!key) return;
    try {
      if (Object.is(value, defaultValue)) {
        window.localStorage.removeItem(key);
      } else {
        window.localStorage.setItem(key, JSON.stringify(value));
      }
    } catch {
      // Blocked storage keeps the value in memory only.
    }
  }, [key, value, defaultValue]);

  return [value, setValue];
}
