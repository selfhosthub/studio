// ui/app/(authenticated)/organization/manage/users/page.tsx

'use client';

import {
  ActionButton,
  StatusBadge,
  SearchInput,
  EmptyState,
  Modal,
  UserAvatar,
  ResourceTable,
  type ResourceColumnConfig,
} from "@/shared/ui";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
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

/**
 * Organization Users page - manages users in the admin's own organization.
 * Uses the same functionality as /organizations/[id]/users but stays within
 * the /organization/manage/ layout for consistent tab navigation.
 */
export default function OrganizationUsersPage() {
  const router = useRouter();
  const { user } = useUser();
  const { toast } = useToast();
  const confirm = useConfirm();
  const orgId = user?.org_id || '';

  const [members, setMembers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInviteModal, setShowInviteModal] = useState(false);

  const [searchTerm, setSearchTerm] = useState('');
  const [inviteForm, setInviteForm] = useState({
    email: '',
    username: '',
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
  const canManageUsers = isSuperAdmin || isAdmin;
  const canView = isSuperAdmin || isAdmin;

  // Redirect if user doesn't have access
  useEffect(() => {
    if (user && !canView) {
      router.push('/dashboard');
    }
  }, [user, canView, router]);

  // Fetch members
  useEffect(() => {
    if (!orgId || !canView) return;

    void (async () => {
      setLoading(true);
      try {
        const data = await getOrganizationMembers(orgId);
        setMembers(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch organization members:', err);
        setError(err instanceof Error ? err.message : 'Failed to load users');
      } finally {
        setLoading(false);
      }
    })();
  }, [orgId, canView]);

  // Filter members by search
  const filteredMembers = useMemo(() => {
    if (!searchTerm) return members;
    const search = searchTerm.toLowerCase();
    return members.filter(m =>
      m.username?.toLowerCase().includes(search) ||
      m.email?.toLowerCase().includes(search) ||
      m.first_name?.toLowerCase().includes(search) ||
      m.last_name?.toLowerCase().includes(search)
    );
  }, [members, searchTerm]);

  const handleDeactivateMember = async (memberId: string, memberName: string) => {
    if (!(await confirm({
      title: 'Deactivate user',
      message: `Deactivate ${memberName}? They cannot sign in until an admin sets them Active again. Their email and username stay reserved.`,
      confirmLabel: 'Deactivate',
      variant: 'warning',
    }))) {
      return;
    }

    try {
      await removeOrganizationMember(orgId, memberId);
      setMembers(prev => prev.map(m => m.id === memberId ? { ...m, is_active: false } : m));
      toast({ title: 'User deactivated', variant: 'success' });
    } catch (err: unknown) {
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

  const handleInviteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteError(null);

    if (inviteForm.password !== inviteForm.confirmPassword) {
      setInviteError('Passwords do not match');
      return;
    }

    try {
      const newUser = await createAndInviteUser(
        orgId,
        inviteForm.email,
        inviteForm.password,
        inviteForm.role,
        inviteForm.username
      );
      setMembers([...members, newUser]);
      setShowInviteModal(false);
      setInviteForm({ email: '', username: '', password: '', confirmPassword: '', role: 'user' });
      toast({ title: 'User added', variant: 'success' });
    } catch (err: unknown) {
      setInviteError(err instanceof Error ? err.message : 'Failed to add user');
    }
  };

  const handleEditClick = (member: any) => {
    setEditingUser(member);
    setEditForm({
      username: member.username || '',
      email: member.email || '',
      first_name: member.first_name || '',
      last_name: member.last_name || '',
      role: member.role || 'user',
      is_active: member.is_active !== false,
    });
    setEditError(null);
  };

  const handleResetPasswordClick = (member: any) => {
    setResetUser(member);
    setResetForm({ password: '', confirmPassword: '' });
    setResetError(null);
  };

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
      setResetError(err instanceof Error ? err.message : 'Failed to reset password');
    } finally {
      setResetSaving(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;

    setEditSaving(true);
    setEditError(null);

    try {
      const updatedUser = await updateUserAsAdmin(editingUser.id, editForm);
      setMembers(members.map(m => m.id === editingUser.id ? { ...m, ...updatedUser } : m));
      setEditingUser(null);
      toast({ title: 'User updated', variant: 'success' });
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : 'Failed to update user');
    } finally {
      setEditSaving(false);
    }
  };

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
      render: (member) => (
        <div className="flex justify-end gap-2 items-center max-md:flex-col max-md:items-stretch">
          <ActionButton variant="change" onClick={() => handleEditClick(member)}>
            Edit
          </ActionButton>
          {member.id !== user?.id && (isSuperAdmin || member.role === 'user') && (
            <ActionButton
              variant="warning"
              onClick={() => handleResetPasswordClick(member)}
            >
              Reset password
            </ActionButton>
          )}
          {member.id !== user?.id && member.is_active !== false && (
            <ActionButton
              variant="warning"
              onClick={() => handleDeactivateMember(member.id, member.username)}
            >
              Deactivate
            </ActionButton>
          )}
        </div>
      ),
    },
  ];

  if (!canView) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-info-subtle rounded-lg">
            <Users className="w-5 h-5 text-info" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-primary">Users ({members.length})</h2>
            <p className="text-sm text-secondary">Manage organization users</p>
          </div>
        </div>
        {canManageUsers && (
          <ActionButton variant="active" onClick={() => setShowInviteModal(true)}>
            Add User
          </ActionButton>
        )}
      </div>

      <ResourceTable
        data={filteredMembers}
        getItemId={(member) => member.id}
        tieBreaker="user"
        columns={columns}
        prefPage="org-users"
        pagination={{ itemLabel: 'user' }}
        pageResetKey={searchTerm}
        toolbar={
          <SearchInput
            value={searchTerm}
            onChange={setSearchTerm}
            placeholder="Search users..."
          />
        }
        loading={loading}
        loadingMessage="Loading users..."
        error={error}
        errorTitle="Error Loading Users"
        onRetry={() => window.location.reload()}
        emptyState={
          <EmptyState
            title="No users found"
            description={searchTerm ? 'Try adjusting your search term.' : 'No users in this organization.'}
          />
        }
      />

      {/* Invite Modal */}
      <Modal isOpen={showInviteModal} onClose={() => setShowInviteModal(false)} title="Add User" size="sm">
        <form onSubmit={handleInviteSubmit} className="p-4 space-y-4">
          <div>
            <label htmlFor="create-user-email" className="block text-sm font-medium text-secondary mb-1">Email</label>
            <input
              id="create-user-email"
              type="email"
              required
              value={inviteForm.email}
              onChange={(e) => updateInviteForm({ email: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="create-user-username" className="block text-sm font-medium text-secondary mb-1">Username</label>
            <input
              id="create-user-username"
              type="text"
              required
              value={inviteForm.username}
              onChange={(e) => updateInviteForm({ username: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="create-user-password" className="block text-sm font-medium text-secondary mb-1">Password</label>
            <input
              id="create-user-password"
              type="password"
              required
              minLength={8}
              value={inviteForm.password}
              onChange={(e) => updateInviteForm({ password: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="create-user-confirm-password" className="block text-sm font-medium text-secondary mb-1">Confirm Password</label>
            <input
              id="create-user-confirm-password"
              type="password"
              required
              minLength={8}
              value={inviteForm.confirmPassword}
              onChange={(e) => updateInviteForm({ confirmPassword: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="create-user-role" className="block text-sm font-medium text-secondary mb-1">Role</label>
            <select
              id="create-user-role"
              value={inviteForm.role}
              onChange={(e) => updateInviteForm({ role: e.target.value as 'user' | 'admin' | 'super_admin' })}
              className="form-input w-full"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          {inviteError && (
            <div className="text-sm text-danger">{inviteError}</div>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-cancel" onClick={() => setShowInviteModal(false)}>
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              Add User
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit Modal */}
      <Modal isOpen={!!editingUser} onClose={() => setEditingUser(null)} title="Edit User" size="sm">
        <form onSubmit={handleEditSubmit} className="p-4 space-y-4">
          <div>
            <label htmlFor="edit-user-username" className="block text-sm font-medium text-secondary mb-1">Username</label>
            <input
              id="edit-user-username"
              type="text"
              value={editForm.username}
              onChange={(e) => updateEditForm({ username: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="edit-user-email" className="block text-sm font-medium text-secondary mb-1">Email</label>
            <input
              id="edit-user-email"
              type="email"
              value={editForm.email}
              onChange={(e) => updateEditForm({ email: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="edit-user-first-name" className="block text-sm font-medium text-secondary mb-1">First Name</label>
              <input
                id="edit-user-first-name"
                type="text"
                value={editForm.first_name}
                onChange={(e) => updateEditForm({ first_name: e.target.value })}
                className="form-input w-full"
              />
            </div>
            <div>
              <label htmlFor="edit-user-last-name" className="block text-sm font-medium text-secondary mb-1">Last Name</label>
              <input
                id="edit-user-last-name"
                type="text"
                value={editForm.last_name}
                onChange={(e) => updateEditForm({ last_name: e.target.value })}
                className="form-input w-full"
              />
            </div>
          </div>
          <div>
            <label htmlFor="edit-user-role" className="block text-sm font-medium text-secondary mb-1">Role</label>
            <select
              id="edit-user-role"
              value={editForm.role}
              onChange={(e) => updateEditForm({ role: e.target.value as 'user' | 'admin' | 'super_admin' })}
              disabled={isEditingSelf}
              className="form-input w-full"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is_active"
              checked={editForm.is_active}
              onChange={(e) => updateEditForm({ is_active: e.target.checked })}
              disabled={isEditingSelf}
              className="form-checkbox"
            />
            <label htmlFor="is_active" className="text-sm text-secondary">Active</label>
          </div>
          {isEditingSelf && (
            <p className="text-xs text-secondary">You cannot change your own role or status</p>
          )}
          {editError && (
            <div className="text-sm text-danger">{editError}</div>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-cancel" onClick={() => setEditingUser(null)} disabled={editSaving}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={editSaving}>
              {editSaving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Reset Password Modal */}
      <Modal isOpen={!!resetUser} onClose={() => setResetUser(null)} title="Reset Password" size="sm">
        <form onSubmit={handleResetPasswordSubmit} className="p-4 space-y-4">
          <p className="text-sm text-secondary">
            Set a one-time password for @{resetUser?.username}. They must change it at next login.
          </p>
          <div>
            <label htmlFor="reset-user-password" className="block text-sm font-medium text-secondary mb-1">New Password</label>
            <input
              id="reset-user-password"
              type="password"
              required
              minLength={8}
              value={resetForm.password}
              onChange={(e) => setResetForm({ ...resetForm, password: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="reset-user-confirm-password" className="block text-sm font-medium text-secondary mb-1">Confirm Password</label>
            <input
              id="reset-user-confirm-password"
              type="password"
              required
              minLength={8}
              value={resetForm.confirmPassword}
              onChange={(e) => setResetForm({ ...resetForm, confirmPassword: e.target.value })}
              className="form-input w-full"
            />
          </div>
          {resetError && (
            <div className="text-sm text-danger">{resetError}</div>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-cancel" onClick={() => setResetUser(null)} disabled={resetSaving}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={resetSaving}>
              {resetSaving ? 'Resetting...' : 'Reset Password'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
