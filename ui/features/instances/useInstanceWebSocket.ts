// ui/features/instances/useInstanceWebSocket.ts

/**
 * useInstanceWebSocket Hook
 *
 * Connects to the WebSocket endpoint for real-time instance status updates.
 * Handles authentication, reconnection, and event processing.
 */

'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { getWsUrl } from '@/shared/lib/config';
import { WEBSOCKET } from '@/shared/lib/constants';

type InstanceStatusChangedEvent = {
  event_type: 'instance_status_changed';
  timestamp: string;
  data: {
    instance_id: string;
    workflow_id: string;
    organization_id: string;
    old_status: string;
    new_status: string;
  };
};

type InstanceDataEvent = {
  event_type: 'instance_data';
  timestamp: string;
  data: {
    instance_id: string;
    workflow_id: string;
    status: string;
    created_at: string | null;
    updated_at: string | null;
  };
};

type ConnectionEstablishedEvent = {
  event_type: 'connection_established';
  timestamp: string;
  data: {
    message: string;
    instance_id: string;
    organization_id: string;
    user_id: string | null;
  };
};

type PongEvent = {
  event_type: 'pong';
  timestamp: string;
  data: Record<string, never>;
};

type InstanceStepCompletedEvent = {
  event_type: 'instance_step_completed';
  timestamp: string;
  data: {
    instance_id: string;
    step_id: string;
    status: string;
  };
};

type InstanceStepStartedEvent = {
  event_type: 'instance_step_started';
  timestamp: string;
  data: {
    instance_id: string;
    step_id: string;
    step_name: string;
    step_status: string;
  };
};

type InstanceStepFailedEvent = {
  event_type: 'instance_step_failed';
  timestamp: string;
  data: {
    instance_id: string;
    step_id: string;
    step_name: string;
    step_status: string;
    error?: string;
  };
};

type InstanceEvent =
  | InstanceStatusChangedEvent
  | InstanceDataEvent
  | ConnectionEstablishedEvent
  | PongEvent
  | InstanceStepCompletedEvent
  | InstanceStepStartedEvent
  | InstanceStepFailedEvent;

type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export function useInstanceWebSocket(instanceId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const [lastEvent, setLastEvent] = useState<InstanceEvent | null>(null);
  const [instanceStatus, setInstanceStatus] = useState<string | null>(null);

  const maxReconnectAttempts = WEBSOCKET.MAX_RECONNECT_ATTEMPTS;
  const reconnectDelay = WEBSOCKET.RECONNECT_DELAY;

  const connect = useCallback(() => {
    if (!instanceId) {
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
      console.warn('[WS] no auth token, skipping connect');
      return;
    }

    try {
      setStatus('connecting');
      const url = `${wsUrl}/ws/instance/${instanceId}`;
      console.log('[WS] connecting', instanceId, url);

      // Use Sec-WebSocket-Protocol header for authentication
      const ws = new WebSocket(url, [`Bearer.${token}`]);
      wsRef.current = ws;

      ws.onopen = () => {
        const wasReconnect = reconnectAttemptsRef.current > 0;
        setStatus('connected');
        if (wasReconnect) {
          console.log('[WS] reconnected after', reconnectAttemptsRef.current, 'attempt(s)', instanceId);
        } else {
          console.log('[WS] connected', instanceId);
        }
        reconnectAttemptsRef.current = 0;
        // Self-healing on reconnect: any events broadcast during the
        // disconnect window are lost (per-connection backpressure /
        // bounded-liveness - broadcast is delivery, not lifecycle; see
        // instance-lifecycle.md §9 guarantee 4). Synthesize a
        // connection_established event so the existing lastEvent watchers
        // in useInstanceLoader fire a fresh instance + jobs refetch.
        if (wasReconnect && instanceId) {
          setLastEvent({
            event_type: 'connection_established',
            timestamp: new Date().toISOString(),
            data: {
              message: 'reconnected',
              instance_id: instanceId,
              organization_id: '',
              user_id: null,
            },
          });
        }
      };

      ws.onmessage = (event) => {
        try {
          const data: InstanceEvent = JSON.parse(event.data);
          setLastEvent(data);
          if (data.event_type !== 'pong') {
            console.log('[WS] event', data.event_type, data);
          }

          // Update instance status based on event type
          if (data.event_type === 'instance_data') {
            setInstanceStatus(data.data.status);
          } else if (data.event_type === 'instance_status_changed') {
            setInstanceStatus(data.data.new_status);
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onerror = () => {
        // Silently handle WebSocket errors - they're expected when backend is not running
        console.warn('[WS] error', instanceId);
        setStatus('error');
      };

      ws.onclose = (event) => {
        console.log('[WS] closed', event.code, event.reason || '(no reason)', instanceId);
        setStatus('disconnected');
        wsRef.current = null;

        // Attempt to reconnect if not a normal closure
        if (event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts) {
          console.log('[WS] scheduling reconnect attempt', reconnectAttemptsRef.current + 1, 'of', maxReconnectAttempts);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current += 1;
            connect();
          }, reconnectDelay);
        } else if (event.code !== 1000) {
          console.warn('[WS] max reconnect attempts reached', instanceId);
        }
      };
    } catch (error) {
      // Silently handle connection errors - they're expected when backend is not running
      setStatus('error');
    }
  }, [instanceId, maxReconnectAttempts, reconnectDelay]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnected');
      wsRef.current = null;
    }

    setStatus('disconnected');
    reconnectAttemptsRef.current = 0;
  }, []);

  // Connect when instanceId is available
  useEffect(() => {
    if (instanceId) {
      connect();
    }

    // Cleanup on unmount or instanceId change
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- connect/disconnect are useCallbacks that depend on instanceId (already listed); adding them triggers immutability error due to self-referencing reconnect pattern
  }, [instanceId]);

  // Send a ping every 30 seconds to keep connection alive
  useEffect(() => {
    if (status !== 'connected' || !wsRef.current) return;

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        console.log('[WS] ping →', instanceId);
        wsRef.current.send(JSON.stringify({ action: 'ping' }));
      }
    }, WEBSOCKET.PING_INTERVAL);

    return () => clearInterval(pingInterval);
  }, [status]);

  return {
    status,
    lastEvent,
    instanceStatus,
    reconnectAttempts: reconnectAttemptsRef.current,
    maxReconnectAttempts,
    connect,
    disconnect,
  };
}
