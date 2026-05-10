// ui/shared/api/users.ts

import { apiRequest } from './core';

export interface UserProfile {
  id: string;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  avatar_url?: string | null;
  role: string;
  org_id?: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
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
  username?: string
): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/organizations/${orgId}/members`, {
    method: 'POST',
    body: JSON.stringify({
      email,
      username: username || email.split('@')[0],
      password,
      role,
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
