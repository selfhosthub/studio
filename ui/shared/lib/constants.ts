// ui/shared/lib/constants.ts

// Operator-tunable values read from NEXT_PUBLIC_* env vars at build time.
// Set in .env before `npm run build` to customize for your deployment.

/**
 * Sentinel that signals a rendered field should be omitted from the outgoing payload.
 * Adapter authors opt in per-field via `| default('__omit__')` in `request_transform`
 * templates. The step editor must reject this literal as a user-entered value, otherwise
 * a user could make their own field vanish from the request.
 */
export const OMIT_SENTINEL = '__omit__';

function envInt(key: string, fallback: number): number {
  const v = process.env[key];
  if (v) {
    const n = parseInt(v, 10);
    if (!isNaN(n)) return n;
  }
  return fallback;
}

/** UI durations in ms. */
export const TIMEOUTS = {
  /** Feedback for copy-to-clipboard actions */
  COPY_FEEDBACK: 2000,
  /** Success/error message auto-dismiss */
  MESSAGE_DISMISS: 3000,
  /** Default toast auto-hide (when no explicit duration) */
  TOAST_DEFAULT: 4000,
  /** Notification auto-dismiss */
  NOTIFICATION_DISMISS: 5000,
  /** Countdown interval for timers */
  COUNTDOWN_INTERVAL: 1000,
  /** Fade-out animation delay for toasts/notifications */
  ANIMATION_FADE: 300,
  /** Layout settle delay for fitView/scroll after render */
  LAYOUT_SETTLE: 150,
  /** Temporary highlight ring on scrolled-to elements */
  HIGHLIGHT_RING: 2000,
} as const;

/** Matches Tailwind's default breakpoints in pixels. */
export const BREAKPOINTS = {
  SM: 640,
  MD: 768,
  LG: 1024,
  XL: 1280,
  XXL: 1536,
} as const;

export const POLLING = {
  DEFAULT: envInt('NEXT_PUBLIC_POLL_DEFAULT_MS', 5000),
  FAST: envInt('NEXT_PUBLIC_POLL_FAST_MS', 2000),
  SLOW: envInt('NEXT_PUBLIC_POLL_SLOW_MS', 30000),
} as const;

export const WEBSOCKET = {
  RECONNECT_DELAY: envInt('NEXT_PUBLIC_WS_RECONNECT_DELAY_MS', 3000),
  MAX_RECONNECT_ATTEMPTS: envInt('NEXT_PUBLIC_WS_MAX_RECONNECT', 5),
  PING_INTERVAL: envInt('NEXT_PUBLIC_WS_PING_INTERVAL_MS', 30000),
  /** Avoid React Strict Mode double-mount on dev. */
  CONNECT_DELAY: envInt('NEXT_PUBLIC_WS_CONNECT_DELAY_MS', 100),
} as const;

export const PAGINATION = {
  DEFAULT_PAGE_SIZE: envInt('NEXT_PUBLIC_PAGE_SIZE_DEFAULT', 20),
  MAX_PAGE_SIZE: envInt('NEXT_PUBLIC_PAGE_SIZE_MAX', 100),
} as const;

export const API_STATUS = {
  RECOVERY_POLL_MS: envInt('NEXT_PUBLIC_API_RECOVERY_POLL_MS', 15000),
  CHECK_TIMEOUT_MS: envInt('NEXT_PUBLIC_API_CHECK_TIMEOUT_MS', 5000),
} as const;

export const LIMITS = {
  MAX_TESTIMONIALS: 3,
} as const;

/** All localStorage keys - import constants rather than literals to keep them discoverable and CI-greppable. */
export const STORAGE_KEYS = {
  INSTANCE_PANEL_WIDTH: 'instance-panel-width',
  RESOURCE_CARD_SIZE: 'resourceCardSize',
  SHOW_THUMBNAILS: 'showThumbnails',
  AUTO_SAVE_COUNTDOWN: 'autoSaveCountdown',
  RECENT_COLORS: 'recent-colors',
  THEME_PREFERENCE: 'studio-theme-preference',
  INSTANCE_VIEW_MODE: 'instanceViewMode',
  SERVICE_PARAMETERS_EXPANDED: 'serviceParametersExpanded',
  USER_PREFERENCES: 'studio-user-preferences',
} as const;

/** Extend this union when adding a new list page - compile-time check enforces consistent localStorage key naming. */
export type ListPageSizeFeature =
  | 'workflows'
  | 'instances'
  | 'providers'
  | 'organizations';

export function listPageSizeKey(feature: ListPageSizeFeature): string {
  return `${feature}-list-pageSize`;
}
