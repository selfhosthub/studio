// ui/shared/api/users.ts

import { apiRequest } from './core';
import type { User } from '@/shared/types/user';

export interface UserProfile {
  id: string;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  avatar_url?: string | null;
  role: string;
  // The /users/me endpoint serializes the org as `organization_id`.
  organization_id?: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

/**
 * Map a DB-sourced /users/me profile to the UI User shape. This is the sole
 * source of identity/role for the UI now that the JWT carries none.
 */
export function profileToUser(profile: UserProfile): User {
  return {
    id: profile.id,
    username: profile.username,
    email: profile.email,
    role: profile.role as User['role'],
    org_id: profile.organization_id,
    first_name: profile.first_name,
    last_name: profile.last_name,
    avatar_url: profile.avatar_url ?? undefined,
  };
}

export interface ChangePasswordResponse {
  message: string;
}

export async function getCurrentUserProfile(): Promise<UserProfile> {
  return apiRequest<UserProfile>('/organizations/users/me');
}

export async function updateCurrentUserProfile(updates: {
  username?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
}): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/organizations/users/me`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

/**
 * Upload a new avatar for a user. Self-only unless admin (enforced by backend).
 * Sends multipart/form-data - do NOT set Content-Type; the browser sets the boundary.
 * Returns the new avatar_url.
 */
export async function uploadUserAvatar(userId: string, file: File): Promise<{ avatar_url: string }> {
  const formData = new FormData();
  formData.append('file', file);
  return apiRequest<{ avatar_url: string }>(`/users/users/${userId}/avatar`, {
    method: 'POST',
    body: formData,
  });
}

/** Remove a user's avatar. Self-only unless admin (enforced by backend). */
export async function deleteUserAvatar(userId: string): Promise<void> {
  await apiRequest<void>(`/users/users/${userId}/avatar`, {
    method: 'DELETE',
  });
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<ChangePasswordResponse> {
  return apiRequest<ChangePasswordResponse>('/organizations/users/me/change-password', {
    method: 'POST',
    body: JSON.stringify({
      current_password: oldPassword,
      new_password: newPassword,
    }),
  });
}

/**
 * Admin only. Sets a one-time password on a member; the member must change it
 * on first login. Org admins reach only their own org's non-admin users.
 */
export async function resetMemberPassword(userId: string, newPassword: string): Promise<void> {
  await apiRequest<void>(`/organizations/users/${userId}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  });
}

/**
 * Admin update of any user. Backend enforces: cannot demote the last admin in an org
 * (even super_admin), can deactivate it for billing/suspension, username + email unique.
 */
export async function updateUserAsAdmin(userId: string, updates: {
  username?: string;
  email?: string;
  role?: 'user' | 'admin' | 'super_admin';
  first_name?: string;
  last_name?: string;
  is_active?: boolean;
}): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/organizations/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

/** Admin only. Username defaults to the email's local part. */
export async function createAndInviteUser(
  orgId: string,
  email: string,
  password: string,
  role: 'user' | 'admin' | 'super_admin',
  username?: string,
  firstName?: string,
  lastName?: string
): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/organizations/${orgId}/members`, {
    method: 'POST',
    body: JSON.stringify({
      email,
      username: username || email.split('@')[0],
      password,
      role,
      ...(firstName ? { first_name: firstName } : {}),
      ...(lastName ? { last_name: lastName } : {}),
    }),
  });
}

/** Admin only. */
export async function addOrganizationMember(
  orgId: string,
  userId: string,
  role: 'user' | 'admin' | 'super_admin'
): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/organizations/${orgId}/members`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, role }),
  });
}

/** Admin only. */
export async function removeOrganizationMember(orgId: string, userId: string): Promise<void> {
  await apiRequest(`/organizations/${orgId}/members/${userId}`, {
    method: 'DELETE',
  });
}
