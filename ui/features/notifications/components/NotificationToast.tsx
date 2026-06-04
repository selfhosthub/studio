// ui/features/notifications/components/NotificationToast.tsx

/**
 * NotificationToast Component
 *
 * Displays a toast notification for real-time incoming notifications.
 */

'use client';

import { useEffect, useState } from 'react';
import { X, Bell } from 'lucide-react';
import { TIMEOUTS } from '@/shared/lib/constants';

type ToastNotification = {
  id: string;
  title?: string;
  message: string;
  timestamp: string;
};

type NotificationToastProps = {
  notification: ToastNotification | null;
  onClose: () => void;
  duration?: number;
};

export default function NotificationToast({
  notification,
  onClose,
  duration = TIMEOUTS.NOTIFICATION_DISMISS
}: NotificationToastProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (!notification) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsVisible(false);
      return;
    }

    // Show toast
    setIsVisible(true);

    // Auto-hide after duration
    const timer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(onClose, TIMEOUTS.ANIMATION_FADE); // Wait for fade-out animation
    }, duration);

    return () => clearTimeout(timer);
  }, [notification, duration, onClose]);

  if (!notification) return null;

  return (
    <div
      className={`fixed top-4 right-4 z-50 max-w-md transition-all duration-300 ${
        isVisible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'
      }`}
    >
      <div className="bg-card rounded-lg shadow-lg border border-primary p-4">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className="flex-shrink-0">
            <div className="w-10 h-10 rounded-full bg-info-subtle flex items-center justify-center">
              <Bell className="w-5 h-5 text-info" />
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            {notification.title && (
              <p className="text-sm font-semibold text-primary mb-1">
                {notification.title}
              </p>
            )}
            <p className="text-sm text-secondary">
              {notification.message}
            </p>
            <p className="text-xs text-secondary mt-1">
              {new Date(notification.timestamp).toLocaleTimeString()}
            </p>
          </div>

          {/* Close button */}
          <button
            onClick={() => {
              setIsVisible(false);
              setTimeout(onClose, TIMEOUTS.ANIMATION_FADE);
            }}
            className="flex-shrink-0 text-muted hover:text-secondary transition-colors"
            aria-label="Close notification"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
