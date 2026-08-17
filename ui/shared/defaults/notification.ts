// ui/shared/defaults/notification.ts

/**
 * Fresh-state defaults for notification UI - what a toast shows when the
 * event carries no title or message of its own.
 *
 * Every consumer reads from this module; nothing inlines the literal.
 * See docs/plans/defaults-consolidation.md for the single-authority rationale.
 */
export interface NotificationDefaults {
  /** Toast heading when the event has no title. */
  toastTitle: string;
  /** Toast body when the event has no message. */
  toastMessage: string;
}

export const NOTIFICATION_DEFAULTS: NotificationDefaults = {
  toastTitle: 'New Notification',
  toastMessage: 'You have a new notification',
};
