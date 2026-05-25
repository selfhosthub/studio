// ui/app/infrastructure/components/MessagingTabPanel.tsx

'use client';

import {
  Activity,
  Wifi,
} from 'lucide-react';
import type { SystemHealthResponse } from '@/shared/api';

interface MessagingTabPanelProps {
  health: SystemHealthResponse;
}

export function MessagingTabPanel({ health }: MessagingTabPanelProps) {
  return (
    <div className="space-y-6">
      {/* Messaging Architecture */}
      <div className="detail-section detail-section-red">
        <div className="detail-section-header">
          <h2 className="section-title flex items-center">
            <Activity className="w-5 h-5 mr-2 text-danger" />
            Direct WebSocket Broadcasting
          </h2>
        </div>
        <div className="detail-section-body">
          <p className="text-sm text-muted">
            Real-time updates are delivered directly via WebSocket connections.
            Workers submit results over HTTP, and the API broadcasts updates to connected clients.
          </p>
        </div>
      </div>

      {/* WebSocket Connections */}
      <div className="detail-section detail-section-red">
        <div className="detail-section-header">
          <div className="flex items-center gap-2">
            <Wifi className="w-5 h-5 text-danger" />
            <h2 className="section-title">WebSocket Connections</h2>
            <span className="text-xs text-muted">(this API instance)</span>
          </div>
        </div>
        <div className="detail-section-body">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="text-center p-3 bg-page rounded-lg border border-primary">
              <p className="text-2xl font-bold text-primary">{health.websocket?.total_connections ?? 0}</p>
              <p className="text-xs text-muted">Total Connections</p>
            </div>
            <div className="text-center p-3 bg-page rounded-lg border border-primary">
              <p className="text-2xl font-bold text-primary">{health.websocket?.organizations_connected ?? 0}</p>
              <p className="text-xs text-muted">Organizations</p>
            </div>
            <div className="text-center p-3 bg-page rounded-lg border border-primary">
              <p className="text-2xl font-bold text-primary">{health.websocket?.users_connected ?? 0}</p>
              <p className="text-xs text-muted">Users</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
