// ui/features/notifications/hooks/useNotificationWebSocket.ts

/**
 * useNotificationWebSocket Hook
 *
 * Connects to the WebSocket endpoint for real-time notification updates.
 * Handles authentication, reconnection, and event processing.
 */

'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useUser } from '@/entities/user';
import { getWsUrl } from '@/shared/lib/config';
import { WEBSOCKET } from '@/shared/lib/constants';

type NotificationEvent = {
  event_type: 'notification_created' | 'notification_sent' | 'notification_read';
  timestamp: string;
  data: {
    notification_id: string;
    channel_type?: string;
    recipient_id?: string;
    organization_id?: string;
    message?: string;
    title?: string;
    priority?: string;
    tags?: string[];
    client_metadata?: Record<string, unknown>;
  };
};

export type MaintenanceEvent = {
  event_type: 'maintenance';
  timestamp: string;
  data: {
    mode: 'warning' | 'enabled' | 'disabled';
    reason?: string | null;
    warning_until?: string | null;
  };
};

type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export function useNotificationWebSocket() {
  const { user } = useUser();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const [lastEvent, setLastEvent] = useState<NotificationEvent | null>(null);
  const [lastMaintenanceEvent, setLastMaintenanceEvent] = useState<MaintenanceEvent | null>(null);

  const maxReconnectAttempts = WEBSOCKET.MAX_RECONNECT_ATTEMPTS;
  const reconnectDelay = WEBSOCKET.RECONNECT_DELAY;

  const connect = useCallback(() => {
    if (!user?.id) {
      // User not available yet
      return;
    }

    // Don't reconnect if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Skip WebSocket in test/e2e mode
    const isE2EMode = process.env.NEXT_PUBLIC_API_ENV === 'e2e';
    if (process.env.NODE_ENV === 'test' || isE2EMode) {
      return;
    }

    // Get WebSocket URL (auto-detects from browser location if env var not set)
    const wsUrl = getWsUrl();
    const token = localStorage.getItem('token');

    if (!token) {
      // No auth token available
      return;
    }

    try {
      setStatus('connecting');
      const url = `${wsUrl}/ws/user/${user.id}`;

      // Use Sec-WebSocket-Protocol header for authentication instead of URL query params
      // This prevents tokens from being logged in server access logs
      const ws = new WebSocket(url, [`Bearer.${token}`]);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          // Handle maintenance events (critical for all logged-in users)
          if (message.event_type === 'maintenance') {
            setLastMaintenanceEvent(message as MaintenanceEvent);
          } else if (message.event_type === 'notification_created' || message.event_type === 'notification_sent' || message.event_type === 'notification_read') {
            setLastEvent(message as NotificationEvent);
          }
          // Ignore other events (pong, connection_established, etc.)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onerror = (error) => {
        // Silently handle WebSocket errors - they're expected when backend is not running
        setStatus('error');
      };

      ws.onclose = (event) => {
        setStatus('disconnected');
        wsRef.current = null;

        // Attempt to reconnect if not a normal closure
        if (event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current += 1;
            connect();
          }, reconnectDelay);
        }
      };
    } catch (error) {
      // Silently handle connection errors - they're expected when backend is not running
      setStatus('error');
    }
  }, [user?.id, maxReconnectAttempts, reconnectDelay]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      // Only close if connection is open or connecting (avoids warning in Strict Mode)
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close(1000, 'User disconnected');
      }
      wsRef.current = null;
    }

    setStatus('disconnected');
    reconnectAttemptsRef.current = 0;
  }, []);

  // Connect when user is available
  useEffect(() => {
    // Delay connection slightly to avoid Strict Mode double-mount connection attempts
    let connectTimeout: NodeJS.Timeout | null = null;
    if (user?.id) {
      connectTimeout = setTimeout(() => {
        connect();
      }, WEBSOCKET.CONNECT_DELAY);
    }

    // Cleanup on unmount or user change
    return () => {
      if (connectTimeout) {
        clearTimeout(connectTimeout);
      }
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- connect/disconnect are useCallbacks that depend on user?.id (already listed); adding them triggers immutability error due to self-referencing reconnect pattern
  }, [user?.id]);

  // Send a ping every 30 seconds to keep connection alive
  useEffect(() => {
    if (status !== 'connected' || !wsRef.current) return;

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'ping' }));
      }
    }, WEBSOCKET.PING_INTERVAL);

    return () => clearInterval(pingInterval);
  }, [status]);

  return {
    status,
    lastEvent,
    lastMaintenanceEvent,
    reconnectAttempts: reconnectAttemptsRef.current,
    maxReconnectAttempts,
    connect,
    disconnect,
  };
}
