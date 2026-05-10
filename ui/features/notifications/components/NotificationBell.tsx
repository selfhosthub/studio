// ui/features/notifications/components/NotificationBell.tsx

/**
 * NotificationBell Component
 *
 * Displays a bell icon with unread notification count badge.
 * Shows a dropdown with recent notifications when clicked.
 * Connects to WebSocket for real-time notification updates.
 */

'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { Bell, X, CheckCheck } from 'lucide-react';
import { useUser } from '@/entities/user';
import { getNotifications, markNotificationAsRead, markAllNotificationsAsRead } from '@/shared/api';
import type { NotificationResponse } from '@/shared/types/api';
import { useNotificationWebSocket } from '../hooks/useNotificationWebSocket';
import { useToast } from '@/features/toast';

export default function NotificationBell() {
  const { user } = useUser();
  const { toast } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // WebSocket connection for real-time updates
  const { status: wsStatus, lastEvent } = useNotificationWebSocket();

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Must be defined before useEffect hooks that reference it (temporal dead zone)
  const fetchNotifications = useCallback(async () => {
    if (!user?.id) return;

    setLoading(true);
    try {
      const data = await getNotifications(user.id);
      setNotifications(data || []);
    } catch {
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  }, [user?.id]);

  // Fetch notifications on mount and when dropdown opens
  useEffect(() => {
    if (user?.id) {
      fetchNotifications();
    }
  }, [user?.id, fetchNotifications]);

  useEffect(() => {
    if (isOpen && user?.id) {
      fetchNotifications();
    }
  }, [isOpen, user?.id, fetchNotifications]);

  // Refetch on WebSocket reconnect to catch notifications missed while disconnected
  const prevWsStatusRef = useRef(wsStatus);
  useEffect(() => {
    const prev = prevWsStatusRef.current;
    prevWsStatusRef.current = wsStatus;
    if (wsStatus === 'connected' && prev !== 'connected' && prev !== undefined && user?.id) {
      fetchNotifications();
    }
  }, [wsStatus, user?.id, fetchNotifications]);

  // Handle incoming WebSocket events
  useEffect(() => {
    if (!lastEvent) return;

    if (lastEvent.event_type === 'notification_created') {
      fetchNotifications();

      // Show toast via global toast system (uses portal, avoids CSS containment issues)
      const title = lastEvent.data.title || 'New Notification';
      const message = lastEvent.data.message || 'You have a new notification';
      const isError = lastEvent.data.tags?.includes('error');
      toast({
        title,
        description: message,
        variant: isError ? 'destructive' : 'success',
      });
    } else if (lastEvent.event_type === 'notification_read') {
      fetchNotifications();
    }
  }, [lastEvent, fetchNotifications, toast]);

  async function handleMarkAsRead(notificationId: string) {
    try {
      await markNotificationAsRead(notificationId);

      // Update local state
      setNotifications(prev =>
        prev.map(notif =>
          notif.id === notificationId
            ? { ...notif, read_at: new Date().toISOString() }
            : notif
        )
      );
    } catch {
      // Silently fail if marking as read fails
    }
  }

  async function handleMarkAllAsRead() {
    if (!user?.id) return;
    try {
      await markAllNotificationsAsRead(user.id);

      const now = new Date().toISOString();
      setNotifications(prev =>
        prev.map(notif => notif.read_at ? notif : { ...notif, read_at: now })
      );
    } catch {
      // Silently fail
    }
  }

  const unreadCount = notifications.filter(n => !n.read_at).length;
  const recentNotifications = notifications.slice(0, 5);

  return (
      <div className="relative" ref={dropdownRef}>
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-full transition-opacity opacity-80 hover:opacity-100 text-info"
        aria-label="Notifications"
        aria-expanded={isOpen}
        data-testid="notification-bell"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span
            className="absolute top-0 right-0 h-5 min-w-[1.25rem] rounded-full bg-danger notification-count text-xs flex items-center justify-center font-medium"
            data-testid="notification-badge"
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 rounded-lg shadow-lg bg-card ring-1 ring-black ring-opacity-5 z-50">
          {/* Header */}
          <div className="px-4 py-3 border-b border-primary flex items-center justify-between">
            <h3 className="text-sm font-semibold text-primary">
              Notifications
            </h3>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllAsRead}
                  className="text-xs text-info hover:text-info flex items-center gap-1"
                  title="Mark all as read"
                >
                  <CheckCheck size={14} />
                  Mark all read
                </button>
              )}
              <button
                onClick={() => setIsOpen(false)}
                className="text-muted hover:text-secondary"
                aria-label="Close notifications"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          {/* Notifications List */}
          <div className="max-h-96 overflow-y-auto">
            {loading ? (
              <div className="px-4 py-6 text-center text-sm text-secondary">
                Loading notifications...
              </div>
            ) : recentNotifications.length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-secondary">
                No notifications
              </div>
            ) : (
              <div className="divide-y divide-primary">
                {recentNotifications.map((notification) => (
                  <div
                    key={notification.id}
                    className={`px-4 py-3 hover:bg-surface transition-colors ${
                      !notification.read_at ? 'bg-info-subtle' : ''
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm ${
                          !notification.read_at
                            ? 'font-medium text-primary'
                            : 'text-secondary'
                        }`}>
                          {notification.message}
                        </p>
                        {notification.created_at && (
                          <p className="text-xs text-secondary mt-1">
                            {new Date(notification.created_at).toLocaleString()}
                          </p>
                        )}
                      </div>
                      {!notification.read_at && (
                        <button
                          onClick={() => handleMarkAsRead(notification.id)}
                          className="ml-2 text-xs text-info hover:text-info whitespace-nowrap"
                        >
                          Mark read
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 border-t border-primary">
            <Link
              href="/notifications"
              className="block text-center text-sm text-info hover:text-info font-medium"
              onClick={() => setIsOpen(false)}
            >
              View all notifications
            </Link>
          </div>
        </div>
      )}
      </div>
  );
}
