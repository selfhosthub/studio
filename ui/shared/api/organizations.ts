// ui/shared/api/organizations.ts

import { apiRequest } from './core';
import type { UserProfile } from './users';
import type { NotificationResponse } from '@/shared/types/api';

export interface Organization {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  settings?: Record<string, any> | null;
  is_active: boolean;
  is_system?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface OrganizationStorageStats {
  files: number;
  size_bytes: number;
  size_formatted: string;
}

export interface OrganizationStats {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  is_active: boolean;
  is_system: boolean;
  created_at?: string | null;
  member_count: number;
  workflow_count: number;
  storage: OrganizationStorageStats;
  plan_name?: string | null;
}

export interface OrganizationStatsListResponse {
  organizations: OrganizationStats[];
  total: number;
  skip: number;
  limit: number;
}

export interface GetOrganizationStatsParams {
  skip?: number;
  limit?: number;
  filter?: 'all' | 'active' | 'inactive' | 'limits_exceeded';
  sort_by?: 'name' | 'created_at' | 'member_count' | 'workflow_count' | 'storage';
  sort_order?: 'asc' | 'desc';
  search?: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body?: string | null;
  is_read: boolean;
  recipient_id: string;
  created_at?: string;
  updated_at?: string;
}

/** Super-admin only. */
export async function getOrganizations(): Promise<Organization[]> {
  return apiRequest<Organization[]>('/organizations/');
}

/** Super-admin only. */
export async function getOrganizationStats(
  params: GetOrganizationStatsParams = {}
): Promise<OrganizationStatsListResponse> {
  const searchParams = new URLSearchParams();
  if (params.skip !== undefined) searchParams.append('skip', params.skip.toString());
  if (params.limit !== undefined) searchParams.append('limit', params.limit.toString());
  if (params.filter) searchParams.append('filter', params.filter);
  if (params.sort_by) searchParams.append('sort_by', params.sort_by);
  if (params.sort_order) searchParams.append('sort_order', params.sort_order);

  const queryString = searchParams.toString();
  const url = queryString ? `/organizations/stats?${queryString}` : '/organizations/stats';
  return apiRequest<OrganizationStatsListResponse>(url);
}

export async function getOrganization(orgId: string): Promise<Organization> {
  return apiRequest<Organization>(`/organizations/${orgId}`);
}

export async function getOrganizationMembers(orgId: string): Promise<UserProfile[]> {
  return apiRequest<UserProfile[]>(`/organizations/${orgId}/members`);
}

export async function createOrganization(data: {
  name: string;
  slug: string;
  description?: string | null;
  settings?: Record<string, any> | null;
}): Promise<Organization> {
  return apiRequest<Organization>('/organizations/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** Admin only. */
export async function updateOrganization(orgId: string, updates: {
  name?: string;
  description?: string;
  settings?: any;
  is_active?: boolean;
}): Promise<Organization> {
  return apiRequest<Organization>(`/organizations/${orgId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function getNotification(notificationId: string): Promise<Notification> {
  return apiRequest<Notification>(`/notifications/notifications/${notificationId}`);
}

export async function getNotifications(userId: string): Promise<NotificationResponse[]> {
  return apiRequest<NotificationResponse[]>(`/notifications/notifications/recipient/${userId}`);
}

export async function markNotificationAsRead(notificationId: string): Promise<void> {
  await apiRequest(`/notifications/notifications/${notificationId}/read`, { method: 'PATCH' });
}

export async function markAllNotificationsAsRead(userId: string): Promise<{ count: number }> {
  return apiRequest<{ count: number }>(`/notifications/notifications/recipient/${userId}/read-all`, { method: 'PATCH' });
}
