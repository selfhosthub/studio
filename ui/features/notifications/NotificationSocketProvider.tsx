// ui/features/notifications/NotificationSocketProvider.tsx

'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useUser } from '@/entities/user';
import { getWsUrl } from '@/shared/lib/config';
import { WEBSOCKET, STORAGE_KEYS } from '@/shared/lib/constants';

export type NotificationEvent = {
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

type NotificationHandler = (event: NotificationEvent) => void;

/**
 * The two payloads on this socket have opposite semantics and are exposed differently.
 *
 * Maintenance is state: latched here, readable at any time, correct for a late reader.
 * Notifications are events: delivered once, on arrival, to whoever is subscribed at
 * that moment, and never replayed to a subscriber that mounts later. Latching them
 * instead would re-fire a stale notification every time a consumer remounts.
 */
interface NotificationSocketValue {
  status: WebSocketStatus;
  lastMaintenanceEvent: MaintenanceEvent | null;
  subscribe: (handler: NotificationHandler) => () => void;
}

const NotificationSocketContext = createContext<NotificationSocketValue | undefined>(undefined);

export function NotificationSocketProvider({ children }: { children: React.ReactNode }) {
  const { user } = useUser();
  const userId = user?.id;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const connectRef = useRef<() => void>(() => {});
  const handlersRef = useRef<Set<NotificationHandler>>(new Set());

  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const [lastMaintenanceEvent, setLastMaintenanceEvent] = useState<MaintenanceEvent | null>(null);

  const subscribe = useCallback((handler: NotificationHandler) => {
    handlersRef.current.add(handler);
    return () => {
      handlersRef.current.delete(handler);
    };
  }, []);

  const connect = useCallback(() => {
    if (!userId) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const isE2EMode = process.env.NEXT_PUBLIC_API_ENV === 'e2e';
    if (process.env.NODE_ENV === 'test' || isE2EMode) return;

    const token = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
    if (!token) return;

    try {
      setStatus('connecting');
      // Auth rides Sec-WebSocket-Protocol so the token stays out of server access logs.
      const ws = new WebSocket(`${getWsUrl()}/ws/user/${userId}`, [`Bearer.${token}`]);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.event_type === 'maintenance') {
            setLastMaintenanceEvent(message as MaintenanceEvent);
          } else if (
            message.event_type === 'notification_created' ||
            message.event_type === 'notification_sent' ||
            message.event_type === 'notification_read'
          ) {
            handlersRef.current.forEach(handler => handler(message as NotificationEvent));
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onerror = () => setStatus('error');

      ws.onclose = (event) => {
        setStatus('disconnected');
        wsRef.current = null;
        if (event.code !== 1000 && reconnectAttemptsRef.current < WEBSOCKET.MAX_RECONNECT_ATTEMPTS) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current += 1;
            connectRef.current();
          }, WEBSOCKET.RECONNECT_DELAY);
        }
      };
    } catch {
      setStatus('error');
    }
  }, [userId]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      const state = wsRef.current.readyState;
      if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) {
        wsRef.current.close(1000, 'User disconnected');
      }
      wsRef.current = null;
    }
    setStatus('disconnected');
    reconnectAttemptsRef.current = 0;
  }, []);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    let connectTimeout: NodeJS.Timeout | null = null;
    if (userId) {
      connectTimeout = setTimeout(() => connect(), WEBSOCKET.CONNECT_DELAY);
    }
    return () => {
      if (connectTimeout) clearTimeout(connectTimeout);
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- connect/disconnect are keyed on userId, which is listed
  }, [userId]);

  useEffect(() => {
    if (status !== 'connected') return;
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'ping' }));
      }
    }, WEBSOCKET.PING_INTERVAL);
    return () => clearInterval(pingInterval);
  }, [status]);

  return (
    <NotificationSocketContext.Provider value={{ status, lastMaintenanceEvent, subscribe }}>
      {children}
    </NotificationSocketContext.Provider>
  );
}

/** Socket status and the latched maintenance state. */
export function useNotificationSocket(): NotificationSocketValue {
  const context = useContext(NotificationSocketContext);
  if (!context) {
    return { status: 'disconnected', lastMaintenanceEvent: null, subscribe: () => () => {} };
  }
  return context;
}

/** Runs handler on each notification event that arrives while mounted. Never replays. */
export function useNotificationEvents(handler: NotificationHandler): void {
  const { subscribe } = useNotificationSocket();
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    return subscribe(event => handlerRef.current(event));
  }, [subscribe]);
}
