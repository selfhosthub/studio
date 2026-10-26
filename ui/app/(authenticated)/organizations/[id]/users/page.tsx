// ui/app/(authenticated)/organizations/[id]/users/page.tsx

"use client";

import {
  ActionButton,
  StatusBadge,
  SearchInput,
  LoadingState,
  ErrorState,
  EmptyState,
  Modal,
  UserAvatar,
  ResourceTable,
  type ResourceColumnConfig,
} from "@/shared/ui";
import { useState, useEffect, useMemo } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  getOrganizationMembers,
  removeOrganizationMember,
  createAndInviteUser,
  updateUserAsAdmin,
  resetMemberPassword
} from "@/shared/api";
import { useUser } from "@/entities/user";
import { useToast } from "@/features/toast";
import { Users } from "lucide-react";
import { useConfirm } from '@/shared/ui/ConfirmDialog';

export default function OrganizationUsersPage() {
  const router = useRouter();
  const params = useParams();
  const { user } = useUser();
  const { toast } = useToast();
  const confirm = useConfirm();
  const orgId = params.id as string;

  const [members, setMembers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInviteModal, setShowInviteModal] = useState(false);

  const [searchTerm, setSearchTerm] = useState('');
  const [inviteForm, setInviteForm] = useState({
    email: '',
    username: '',
    first_name: '',
    last_name: '',
    password: '',
    confirmPassword: '',
    role: 'user' as 'user' | 'admin' | 'super_admin',
  });
  const [inviteError, setInviteError] = useState<string | null>(null);

  // Edit user state
  const [editingUser, setEditingUser] = useState<any | null>(null);
  const [editForm, setEditForm] = useState({
    username: '',
    email: '',
    first_name: '',
    last_name: '',
    role: 'user' as 'user' | 'admin' | 'super_admin',
    is_active: true,
  });
  const [editError, setEditError] = useState<string | null>(null);
  const [editSaving, setEditSaving] = useState(false);

  // Reset password state
  const [resetUser, setResetUser] = useState<any | null>(null);
  const [resetForm, setResetForm] = useState({ password: '', confirmPassword: '' });
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetSaving, setResetSaving] = useState(false);

  // Check permissions
  const isSuperAdmin = user?.role === 'super_admin';
  const isAdmin = user?.role === 'admin';
  const isViewingOtherOrg = isSuperAdmin && user?.org_id !== orgId;
  // Super-admin can always manage users (activate/deactivate, promote/demote)
  // Admin can manage users in their own org
  const canManageUsers = isSuperAdmin || (isAdmin && user?.org_id === orgId);
  // Only admins and super_admins can view user lists
  const canView = isSuperAdmin || (isAdmin && user?.org_id === orgId);

  // Redirect if user doesn't have access
  useEffect(() => {
    if (user && !canView) {
      router.push('/dashboard');
    }
  }, [user, canView, router]);

  // Fetch members
  useEffect(() => {
    if (!user) return;
    if (!canView) return;

    getOrganizationMembers(orgId)
      .then((membersData) => {
        setMembers(membersData);
        setError(null);
      })
      .catch((err) => {
        console.error('Failed to fetch members:', err);
        setError('Failed to load users');
      })
      .finally(() => setLoading(false));
  }, [orgId, canView, user]);

  // Filter members based on search
  const filteredMembers = useMemo(() => {
    return members.filter(
      (member) =>
        member.username?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        member.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        member.first_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        member.last_name?.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [members, searchTerm]);

  const totalCount = filteredMembers.length;

  // Handle edit user - open modal
  const handleEditUser = (member: any) => {
    setEditingUser(member);
    setEditForm({
      username: member.username || '',
      email: member.email || '',
      first_name: member.first_name || '',
      last_name: member.last_name || '',
      role: member.role || 'user',
      is_active: member.is_active ?? true,
    });
    setEditError(null);
  };

  // Handle save user edits
  const handleSaveUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;

    setEditSaving(true);
    setEditError(null);

    try {
      await updateUserAsAdmin(editingUser.id, {
        username: editForm.username,
        email: editForm.email,
        first_name: editForm.first_name,
        last_name: editForm.last_name,
        role: editForm.role,
        is_active: editForm.is_active,
      });

      // Reload members list
      const updatedMembers = await getOrganizationMembers(orgId);
      setMembers(updatedMembers);
      setEditingUser(null);
      toast({ title: 'User updated', variant: 'success' });
    } catch (err: unknown) {
      console.error('Failed to update user:', err);
      setEditError(err instanceof Error ? err.message : 'Failed to update user');
    } finally {
      setEditSaving(false);
    }
  };

  // Handle reset password - open modal
  const handleResetPasswordClick = (member: any) => {
    setResetUser(member);
    setResetForm({ password: '', confirmPassword: '' });
    setResetError(null);
  };

  // Handle reset password submit
  const handleResetPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetUser) return;

    if (resetForm.password !== resetForm.confirmPassword) {
      setResetError('Passwords do not match');
      return;
    }

    if (resetForm.password.length < 8) {
      setResetError('Password must be at least 8 characters');
      return;
    }

    setResetSaving(true);
    setResetError(null);

    try {
      await resetMemberPassword(resetUser.id, resetForm.password);
      setResetUser(null);
      toast({ title: 'Password reset', description: 'The user must change it at next login.', variant: 'success' });
    } catch (err: unknown) {
      console.error('Failed to reset password:', err);
      setResetError(err instanceof Error ? err.message : 'Failed to reset password');
    } finally {
      setResetSaving(false);
    }
  };

  // Handle deactivate member
  const handleDeactivateMember = async (userId: string, username: string) => {
    if (!(await confirm({
      title: 'Deactivate user',
      message: `Deactivate ${username}? They cannot sign in until an admin sets them Active again. Their email and username stay reserved.`,
      confirmLabel: 'Deactivate',
      variant: 'warning',
    }))) {
      return;
    }

    try {
      await removeOrganizationMember(orgId, userId);
      const members = await getOrganizationMembers(orgId);
      setMembers(members);
      toast({ title: 'User deactivated', variant: 'success' });
    } catch (err: unknown) {
      console.error('Failed to deactivate member:', err);
      toast({ title: 'Deactivate failed', description: err instanceof Error ? err.message : 'Failed to deactivate user', variant: 'destructive' });
    }
  };

  const updateInviteForm = (patch: Partial<typeof inviteForm>) => {
    setInviteForm({ ...inviteForm, ...patch });
    setInviteError(null);
  };

  const updateEditForm = (patch: Partial<typeof editForm>) => {
    setEditForm({ ...editForm, ...patch });
    setEditError(null);
  };

  const isEditingSelf = editingUser?.id === user?.id;

  // Handle invite user
  const handleInviteUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteError(null);

    if (!inviteForm.email.trim()) {
      setInviteError('Email is required');
      return;
    }

    if (!inviteForm.password.trim()) {
      setInviteError('Password is required');
      return;
    }

    if (inviteForm.password !== inviteForm.confirmPassword) {
      setInviteError('Passwords do not match');
      return;
    }

    if (inviteForm.password.length < 8) {
      setInviteError('Password must be at least 8 characters');
      return;
    }

    try {
      await createAndInviteUser(
        orgId,
        inviteForm.email,
        inviteForm.password,
        inviteForm.role,
        inviteForm.username || undefined,
        inviteForm.first_name || undefined,
        inviteForm.last_name || undefined
      );
      toast({ title: 'User added', variant: 'success' });
      setShowInviteModal(false);
      setInviteForm({ email: '', username: '', first_name: '', last_name: '', password: '', confirmPassword: '', role: 'user' });
      // Reload members list
      const members = await getOrganizationMembers(orgId);
      setMembers(members);
    } catch (err: unknown) {
      console.error('Failed to create user:', err);
      setInviteError(err instanceof Error ? err.message : 'Failed to add user');
    }
  };

  const adminCount = members.filter(m => m.role === 'admin').length;

  const columns: ResourceColumnConfig<any>[] = [
    {
      key: 'user',
      header: 'User',
      sortValue: (member) => (member.first_name && member.last_name
        ? `${member.first_name} ${member.last_name}`
        : member.username),
      render: (member) => (
        <div className="flex items-center">
          <UserAvatar user={member} sizeClassName="w-8 h-8" />
          <div className="ml-3">
            <div className="text-sm font-medium text-primary">
              {member.first_name && member.last_name
                ? `${member.first_name} ${member.last_name}`
                : member.username}
            </div>
            <div className="text-sm text-secondary">@{member.username}</div>
          </div>
        </div>
      ),
    },
    {
      key: 'email',
      header: 'Email',
      sortValue: (member) => member.email,
      cellClassName: 'whitespace-nowrap text-sm text-secondary',
      render: (member) => member.email,
    },
    {
      key: 'role',
      header: 'Role',
      sortValue: (member) => member.role,
      cellClassName: 'md:whitespace-nowrap',
      render: (member) => (
        <StatusBadge
          status={member.role}
          variant={member.role === 'admin' ? 'warning' : member.role === 'super_admin' ? 'error' : 'default'}
        />
      ),
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (member) => member.is_active !== false,
      priority: 'primary',
      cellClassName: 'md:whitespace-nowrap',
      render: (member) => (
        <StatusBadge
          status={member.is_active !== false ? 'active' : 'inactive'}
          variant={member.is_active !== false ? 'success' : 'default'}
        />
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      visible: canManageUsers,
      cellClassName: 'md:whitespace-nowrap text-sm',
      render: (member) => {
        const isMemberSuperAdmin = member.role === 'super_admin';
        const isCurrentUserSuperAdmin = user?.role === 'super_admin';
        // Check if member is the only admin in the org
        const isOnlyAdmin = member.role === 'admin' && adminCount === 1;
        // Hide deactivate for super_admin users, sole org admins, yourself and inactive members
        const canDeactivate = !isMemberSuperAdmin && !isOnlyAdmin && member.id !== user?.id && member.is_active !== false;
        // Super admins can edit anyone; others can edit non-super_admins
        const canEdit = canManageUsers && (isCurrentUserSuperAdmin || !isMemberSuperAdmin);
        // Super admins can reset anyone's password; org admins only non-admin users. Never self.
        const canResetPassword = member.id !== user?.id &&
          (isCurrentUserSuperAdmin || member.role === 'user');

        return (
          <div className="flex justify-end gap-2 items-center max-md:flex-col max-md:items-stretch">
            {canEdit && (
              <ActionButton variant="change" onClick={() => handleEditUser(member)}>
                Edit
              </ActionButton>
            )}
            {canResetPassword && (
              <ActionButton variant="warning" onClick={() => handleResetPasswordClick(member)}>
                Reset password
              </ActionButton>
            )}
            {canDeactivate && (
              <ActionButton
                variant="warning"
                onClick={() => handleDeactivateMember(member.id, member.username)}
              >
                Deactivate
              </ActionButton>
            )}
          </div>
        );
      },
    },
  ];

  if (!canView) {
    return null;
  }

  if (loading) {
    return <LoadingState message="Loading users..." />;
  }

  if (error) {
    return (
      <ErrorState
        title="Error Loading Users"
        message={error}
        onRetry={() => window.location.reload()}
        retryLabel="Try Again"
      />
    );
  }

  return (
    <>
      {/* Members List */}
      <div className="bg-card shadow overflow-hidden sm:rounded-lg">
        <div className="px-4 py-5 sm:px-6 flex justify-between items-start">
          <div>
            <h3 className="text-lg leading-6 font-medium text-primary">
              Users ({totalCount})
            </h3>
            <p className="mt-1 max-w-2xl text-sm text-secondary">
              {canManageUsers ? 'Manage organization users' : 'View organization users'}
            </p>
          </div>
          {canManageUsers && (
            <ActionButton variant="active" onClick={() => setShowInviteModal(true)}>
              Add User
            </ActionButton>
          )}
        </div>

        <div className="px-4 py-4 border-t border-primary">
          <ResourceTable
            data={filteredMembers}
            getItemId={(member) => member.id}
            tieBreaker="user"
            columns={columns}
            prefPage="organization-users"
            pagination={{ itemLabel: 'user' }}
            pageResetKey={searchTerm}
            toolbar={
              <SearchInput
                value={searchTerm}
                onChange={setSearchTerm}
                placeholder="Search users..."
              />
            }
            emptyState={
              <EmptyState
                icon={<Users className="h-12 w-12" />}
                title="No users found"
                description={searchTerm ? 'Try adjusting your search term.' : 'No users in this organization.'}
              />
            }
          />
        </div>
      </div>

      {/* Invite User Modal */}
      <Modal isOpen={showInviteModal} onClose={() => { setShowInviteModal(false); setInviteError(null); }} title="Add User" size="md">
        <form onSubmit={handleInviteUser}>
          <div className="p-4 space-y-4">
            {inviteError && (
              <div className="alert alert-error">
                <p className="text-sm text-danger">{inviteError}</p>
              </div>
            )}

            <div>
              <label htmlFor="email" className="form-label">
                Email *
              </label>
              <input
                type="email"
                id="email"
                required
                value={inviteForm.email}
                onChange={(e) => updateInviteForm({ email: e.target.value })}
                className="form-input"
                placeholder="user@example.com"
              />
            </div>

            <div>
              <label htmlFor="username" className="form-label">
                Username (optional)
              </label>
              <input
                type="text"
                id="username"
                value={inviteForm.username}
                onChange={(e) => updateInviteForm({ username: e.target.value })}
                className="form-input"
                placeholder="Defaults to email prefix"
              />
              <p className="mt-1 text-xs text-secondary">
                If not provided, will use the part before @ in email
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="first_name" className="form-label">
                  First Name (optional)
                </label>
                <input
                  type="text"
                  id="first_name"
                  value={inviteForm.first_name}
                  onChange={(e) => updateInviteForm({ first_name: e.target.value })}
                  className="form-input"
                />
              </div>
              <div>
                <label htmlFor="last_name" className="form-label">
                  Last Name (optional)
                </label>
                <input
                  type="text"
                  id="last_name"
                  value={inviteForm.last_name}
                  onChange={(e) => updateInviteForm({ last_name: e.target.value })}
                  className="form-input"
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="form-label">
                Password *
              </label>
              <input
                type="password"
                id="password"
                required
                minLength={8}
                value={inviteForm.password}
                onChange={(e) => updateInviteForm({ password: e.target.value })}
                className="form-input"
                placeholder="Minimum 8 characters"
              />
            </div>

            <div>
              <label htmlFor="confirmPassword" className="form-label">
                Confirm Password *
              </label>
              <input
                type="password"
                id="confirmPassword"
                required
                minLength={8}
                value={inviteForm.confirmPassword}
                onChange={(e) => updateInviteForm({ confirmPassword: e.target.value })}
                className="form-input"
                placeholder="Re-enter password"
              />
            </div>

            <div>
              <label htmlFor="role" className="form-label">
                Role *
              </label>
              <select
                id="role"
                value={inviteForm.role}
                onChange={(e) => updateInviteForm({ role: e.target.value as 'user' | 'admin' | 'super_admin' })}
                className="form-input"
              >
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
              <p className="mt-1 text-xs text-secondary">
                Admins can manage organization users and settings
              </p>
            </div>
          </div>
          <div className="bg-surface px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
            <button
              type="submit"
              className="btn-primary w-full sm:ml-3 sm:w-auto"
            >
              Add User
            </button>
            <button
              type="button"
              onClick={() => {
                setShowInviteModal(false);
                setInviteError(null);
                setInviteForm({ email: '', username: '', first_name: '', last_name: '', password: '', confirmPassword: '', role: 'user' });
              }}
              className="btn-cancel mt-3 w-full inline-flex justify-center text-base sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit User Modal */}
      <Modal isOpen={!!editingUser} onClose={() => setEditingUser(null)} title="Edit User" size="md">
        <form onSubmit={handleSaveUser}>
          <div className="p-4 space-y-4">
            {editError && (
              <div className="alert alert-error">
                <p className="text-sm text-danger">{editError}</p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="edit-first-name" className="form-label">
                  First Name
                </label>
                <input
                  type="text"
                  id="edit-first-name"
                  value={editForm.first_name}
                  onChange={(e) => updateEditForm({ first_name: e.target.value })}
                  className="form-input"
                />
              </div>
              <div>
                <label htmlFor="edit-last-name" className="form-label">
                  Last Name
                </label>
                <input
                  type="text"
                  id="edit-last-name"
                  value={editForm.last_name}
                  onChange={(e) => updateEditForm({ last_name: e.target.value })}
                  className="form-input"
                />
              </div>
            </div>

            <div>
              <label htmlFor="edit-username" className="form-label">
                Username
              </label>
              <input
                type="text"
                id="edit-username"
                value={editForm.username}
                onChange={(e) => updateEditForm({ username: e.target.value })}
                className="form-input"
              />
            </div>

            <div>
              <label htmlFor="edit-email" className="form-label">
                Email
              </label>
              <input
                type="email"
                id="edit-email"
                value={editForm.email}
                onChange={(e) => updateEditForm({ email: e.target.value })}
                className="form-input"
              />
            </div>

            {(() => {
              // Super admins cannot have their role changed via org management
              // They are a platform-level concept, not an org-level one
              const isEditingSuperAdmin = editingUser?.role === 'super_admin';
              const canChangeStatus = !isEditingSuperAdmin && !isEditingSelf;

              return (
                <>
                  <div>
                    <label htmlFor="edit-role" className="form-label">
                      Role
                    </label>
                    {isEditingSuperAdmin ? (
                      <p className="mt-1 px-3 py-2 bg-card rounded-md text-primary text-sm">
                        Super Admin (platform-level)
                      </p>
                    ) : (
                      <select
                        id="edit-role"
                        value={editForm.role}
                        onChange={(e) => updateEditForm({ role: e.target.value as 'user' | 'admin' })}
                        disabled={isEditingSelf}
                        className="form-input"
                      >
                        <option value="user">User</option>
                        <option value="admin">Admin</option>
                      </select>
                    )}
                    {isEditingSuperAdmin && (
                      <p className="mt-1 text-xs text-secondary">
                        Super admin role is managed at the platform level
                      </p>
                    )}
                  </div>

                  <div>
                    <label htmlFor="edit-status" className="form-label">
                      Status
                    </label>
                    <select
                      id="edit-status"
                      value={editForm.is_active ? 'active' : 'inactive'}
                      onChange={(e) => updateEditForm({ is_active: e.target.value === 'active' })}
                      className="mt-1 block w-full rounded-md border border-primary shadow-sm focus:border-info focus:ring-blue-500 bg-surface sm:text-sm px-3 py-2 disabled:opacity-60 disabled:cursor-not-allowed"
                      disabled={!canChangeStatus}
                    >
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                    </select>
                    {isEditingSuperAdmin && (
                      <p className="mt-1 text-xs text-secondary">
                        Super admin status is managed at the platform level
                      </p>
                    )}
                    {isEditingSelf && !isEditingSuperAdmin && (
                      <p className="mt-1 text-xs text-secondary">
                        You cannot change your own role or status
                      </p>
                    )}
                  </div>
                </>
              );
            })()}
          </div>
          <div className="bg-surface px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
            <button
              type="submit"
              disabled={editSaving}
              className="btn-primary w-full sm:ml-3 sm:w-auto"
            >
              {editSaving ? 'Saving...' : 'Save'}
            </button>
            <button
              type="button"
              onClick={() => {
                setEditingUser(null);
                setEditError(null);
              }}
              className="btn-cancel mt-3 w-full inline-flex justify-center text-base sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      {/* Reset Password Modal */}
      <Modal isOpen={!!resetUser} onClose={() => setResetUser(null)} title="Reset Password" size="md">
        <form onSubmit={handleResetPasswordSubmit}>
          <div className="p-4 space-y-4">
            {resetError && (
              <div className="alert alert-error">
                <p className="text-sm text-danger">{resetError}</p>
              </div>
            )}

            <p className="text-sm text-secondary">
              Set a one-time password for @{resetUser?.username}. They must change it at next login.
            </p>

            <div>
              <label htmlFor="reset-password" className="form-label">
                New Password *
              </label>
              <input
                type="password"
                id="reset-password"
                required
                minLength={8}
                value={resetForm.password}
                onChange={(e) => setResetForm({ ...resetForm, password: e.target.value })}
                className="form-input"
                placeholder="Minimum 8 characters"
              />
            </div>

            <div>
              <label htmlFor="reset-confirm-password" className="form-label">
                Confirm Password *
              </label>
              <input
                type="password"
                id="reset-confirm-password"
                required
                minLength={8}
                value={resetForm.confirmPassword}
                onChange={(e) => setResetForm({ ...resetForm, confirmPassword: e.target.value })}
                className="form-input"
                placeholder="Re-enter password"
              />
            </div>
          </div>
          <div className="bg-surface px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
            <button
              type="submit"
              disabled={resetSaving}
              className="btn-primary w-full sm:ml-3 sm:w-auto"
            >
              {resetSaving ? 'Resetting...' : 'Reset Password'}
            </button>
            <button
              type="button"
              onClick={() => {
                setResetUser(null);
                setResetError(null);
              }}
              className="btn-cancel mt-3 w-full inline-flex justify-center text-base sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}
