// ui/features/maintenance/hooks/useMaintenance.ts

/**
 * useMaintenance Hook
 *
 * Checks if the site is in maintenance mode via the public API on mount,
 * then listens for WebSocket events for real-time updates.
 *
 * Also drives the shared API status tracker - calls markApiUp()/markApiDown()
 * based on whether the maintenance endpoint is reachable. Other hooks gate
 * their fetches on API status to prevent redundant failed requests.
 *
 * For authenticated users, maintenance events come via the user WebSocket
 * (passed in via maintenanceEvent prop). For unauthenticated users (login page),
 * falls back to the public WebSocket endpoint.
 */

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { getWsUrl } from '@/shared/lib/config';
import { markApiUp, markApiDown, getApiStatus } from '@/shared/lib/api-status';
import { publicApiRequest } from '@/shared/api';
import { useApiStatus } from '@/shared/hooks/useApiStatus';
import { WEBSOCKET } from '@/shared/lib/constants';
import { type MaintenanceEvent } from '@/features/notifications';

interface MaintenanceStatus {
  maintenanceMode: boolean;
  warningMode: boolean;
  warningUntil: Date | null;
  reason: string | null;
  isLoading: boolean;
}

interface UseMaintenanceOptions {
  /** Maintenance event from authenticated WebSocket (for logged-in users) */
  maintenanceEvent?: MaintenanceEvent | null;
}

export function useMaintenance(options?: UseMaintenanceOptions): MaintenanceStatus {
  const { maintenanceEvent } = options || {};
  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [warningMode, setWarningMode] = useState(false);
  const [warningUntil, setWarningUntil] = useState<Date | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Subscribe to API status for WebSocket gating
  const apiStatus = useApiStatus();

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = WEBSOCKET.MAX_RECONNECT_ATTEMPTS;
  const reconnectDelay = WEBSOCKET.RECONNECT_DELAY;

  // Handle a maintenance event (from WebSocket or initial HTTP check)
  const handleMaintenanceUpdate = useCallback((data: {
    mode?: string;
    maintenance_mode?: boolean;
    warning_mode?: boolean;
    reason?: string | null;
    warning_until?: string | null;
  }) => {
    // Handle WebSocket event format
    if (data.mode) {
      switch (data.mode) {
        case 'warning':
          setMaintenanceMode(false);
          setWarningMode(true);
          setReason(data.reason || null);
          if (data.warning_until) {
            setWarningUntil(new Date(data.warning_until));
          }
          break;
        case 'enabled':
          setMaintenanceMode(true);
          setWarningMode(false);
          setReason(data.reason || null);
          setWarningUntil(null);
          break;
        case 'disabled':
          setMaintenanceMode(false);
          setWarningMode(false);
          setReason(null);
          setWarningUntil(null);
          break;
      }
    } else {
      // Handle HTTP API response format
      setMaintenanceMode(data.maintenance_mode === true);
      setWarningMode(data.warning_mode === true);
      setReason(data.reason || null);
      if (data.warning_until) {
        setWarningUntil(new Date(data.warning_until));
      } else {
        setWarningUntil(null);
      }
    }
  }, []);

  // Check maintenance status via HTTP
  const checkMaintenance = useCallback(async () => {
    try {
      const data = await publicApiRequest<{
        maintenance_mode?: boolean;
        warning_mode?: boolean;
        reason?: string | null;
        warning_until?: string | null;
      }>('/public/maintenance');
      handleMaintenanceUpdate(data);
      markApiUp();
    } catch (err: unknown) {
      if (err instanceof Error && err.message.startsWith('API error:')) {
        // Non-OK but reachable - API is up, just not in maintenance
        setMaintenanceMode(false);
        setWarningMode(false);
        setWarningUntil(null);
        setReason(null);
        markApiUp();
      } else {
        // Network error - API is unreachable
        setMaintenanceMode(false);
        setWarningMode(false);
        setWarningUntil(null);
        setReason(null);
        markApiDown();
      }
    } finally {
      setIsLoading(false);
    }
  }, [handleMaintenanceUpdate]);

  // Connect to WebSocket for real-time updates
  const connectWebSocket = useCallback(() => {
    // Don't connect if API is known to be down
    if (getApiStatus() === 'down') return;

    // Don't reconnect if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Skip WebSocket in test/e2e mode or server-side
    if (typeof window === 'undefined') {
      return;
    }
    const isE2EMode = process.env.NEXT_PUBLIC_API_ENV === 'e2e';
    if (process.env.NODE_ENV === 'test' || isE2EMode) {
      return;
    }

    try {
      const wsUrl = getWsUrl();
      // Use the public WebSocket endpoint for maintenance updates (no auth required)
      const url = `${wsUrl}/ws/public`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          // Handle maintenance events
          if (message.event_type === 'maintenance') {
            handleMaintenanceUpdate(message.data);
          }
        } catch {
          // Ignore parse errors
        }
      };

      ws.onerror = () => {
        // Silently handle WebSocket errors
      };

      ws.onclose = (event) => {
        wsRef.current = null;

        // Don't reconnect if API is known to be down
        if (getApiStatus() === 'down') return;

        // Attempt to reconnect if not a normal closure
        if (event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current += 1;
            connectWebSocket();
          }, reconnectDelay);
        }
      };
    } catch {
      // Silently handle connection errors
    }
  }, [handleMaintenanceUpdate, maxReconnectAttempts, reconnectDelay]);

  const disconnectWebSocket = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      // Only close if connection is open or connecting (avoids warning in Strict Mode)
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close(1000, 'Component unmounted');
      }
      wsRef.current = null;
    }

    reconnectAttemptsRef.current = 0;
  }, []);

  // Handle maintenance events from authenticated WebSocket (for logged-in users)
  useEffect(() => {
    if (maintenanceEvent) {
      handleMaintenanceUpdate(maintenanceEvent.data);
    }
  }, [maintenanceEvent, handleMaintenanceUpdate]);

  // Initial HTTP check - fires on mount, drives API status for all hooks
  useEffect(() => {
    checkMaintenance();
  }, [checkMaintenance]);

  // WebSocket connection - only when API is confirmed reachable
  useEffect(() => {
    // Don't connect WebSocket if API is not up or if using authenticated WS
    if (apiStatus !== 'up' || maintenanceEvent) return;

    const connectTimeout = setTimeout(connectWebSocket, WEBSOCKET.CONNECT_DELAY);

    return () => {
      clearTimeout(connectTimeout);
      disconnectWebSocket();
    };
  }, [apiStatus, maintenanceEvent, connectWebSocket, disconnectWebSocket]);

  // Send ping every 30 seconds to keep connection alive
  useEffect(() => {
    if (!wsRef.current) return;

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'ping' }));
      }
    }, WEBSOCKET.PING_INTERVAL);

    return () => clearInterval(pingInterval);
  }, []);

  return { maintenanceMode, warningMode, warningUntil, reason, isLoading };
}
