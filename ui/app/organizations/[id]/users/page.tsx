// ui/app/organizations/[id]/users/page.tsx

"use client";

import {
  ActionButton,
  StatusBadge,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
  Modal,
  UserAvatar,
} from "@/shared/ui";
import { useState, useEffect, useMemo } from "react";
import { PAGINATION } from '@/shared/lib/constants';
import { useRouter, useParams } from "next/navigation";
import {
  getOrganizationMembers,
  removeOrganizationMember,
  createAndInviteUser,
  updateUserAsAdmin
} from "@/shared/api";
import { useUser } from "@/entities/user";
import { useToast } from "@/features/toast";
import { Users } from "lucide-react";
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';

export default function OrganizationUsersPage() {
  const router = useRouter();
  const params = useParams();
  const { user } = useUser();
  const { toast } = useToast();
  const orgId = params.id as string;

  const [members, setMembers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInviteModal, setShowInviteModal] = useState(false);

  // Search and pagination state
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGINATION.DEFAULT_PAGE_SIZE);
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
        setError('Failed to load members');
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

  // Reset page when search changes (adjust during render, not in an effect).
  const [prevSearchTerm, setPrevSearchTerm] = useState(searchTerm);
  if (searchTerm !== prevSearchTerm) {
    setPrevSearchTerm(searchTerm);
    setCurrentPage(1);
  }

  // Pagination calculations
  const totalCount = filteredMembers.length;
  const totalPages = Math.ceil(totalCount / pageSize) || 1;

  // Apply pagination
  const paginatedMembers = filteredMembers.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

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

  // Handle remove member
  const handleRemoveMember = async (userId: string, username: string) => {
    if (!confirm(`Are you sure you want to remove ${username} from this organization?`)) {
      return;
    }

    try {
      await removeOrganizationMember(orgId, userId);
      const members = await getOrganizationMembers(orgId);
      setMembers(members);
      toast({ title: 'Member removed', variant: 'success' });
    } catch (err: unknown) {
      console.error('Failed to remove member:', err);
      toast({ title: 'Remove failed', description: err instanceof Error ? err.message : 'Failed to remove member', variant: 'destructive' });
    }
  };

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
      toast({ title: 'User created', description: 'User created and added to organization successfully!', variant: 'success' });
      setShowInviteModal(false);
      setInviteForm({ email: '', username: '', first_name: '', last_name: '', password: '', confirmPassword: '', role: 'user' });
      // Reload members list
      const members = await getOrganizationMembers(orgId);
      setMembers(members);
    } catch (err: unknown) {
      console.error('Failed to create user:', err);
      setInviteError(err instanceof Error ? err.message : 'Failed to create user');
    }
  };

  if (!canView) {
    return null;
  }

  if (loading) {
    return <LoadingState message="Loading members..." />;
  }

  if (error) {
    return (
      <ErrorState
        title="Error Loading Members"
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
              Members ({totalCount})
            </h3>
            <p className="mt-1 max-w-2xl text-sm text-secondary">
              {canManageUsers ? 'Manage organization members' : 'View organization members'}
            </p>
          </div>
          {canManageUsers && (
            <ActionButton variant="active" onClick={() => setShowInviteModal(true)}>
              Invite User
            </ActionButton>
          )}
        </div>

        {/* Search and Pagination Controls */}
        <div className="px-4 py-4 border-t border-primary">
          <div className="flex items-center justify-between gap-4">
            <SearchInput
              value={searchTerm}
              onChange={setSearchTerm}
              placeholder="Search members..."
            />
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalCount={totalCount}
              pageSize={pageSize}
              onPageChange={setCurrentPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setCurrentPage(1);
              }}
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              position="top"
            />
          </div>
        </div>

        <div className="border-t border-primary">
          {paginatedMembers.length === 0 ? (
            <EmptyState
              icon={<Users className="h-12 w-12" />}
              title="No members found"
              description={searchTerm ? 'Try adjusting your search term.' : 'No members in this organization.'}
            />
          ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-primary">
              <thead className="bg-surface">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-secondary uppercase">User</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-secondary uppercase">Email</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-secondary uppercase">Role</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-secondary uppercase">Status</th>
                  {canManageUsers && (
                    <th className="px-4 py-3 text-right text-xs font-medium text-secondary uppercase">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="bg-card divide-y divide-primary">
                {paginatedMembers.map((member) => {
                  const isMemberSuperAdmin = member.role === 'super_admin';
                  const isCurrentUserSuperAdmin = user?.role === 'super_admin';
                  // Check if member is the only admin in the org
                  const adminCount = members.filter(m => m.role === 'admin').length;
                  const isOnlyAdmin = member.role === 'admin' && adminCount === 1;
                  // Hide remove for super_admin users and sole org admins
                  const canRemove = !isMemberSuperAdmin && !isOnlyAdmin;
                  // Super admins can edit anyone; others can edit non-super_admins
                  const canEdit = canManageUsers && (isCurrentUserSuperAdmin || !isMemberSuperAdmin);

                  return (
                    <tr key={member.id}>
                      <td className="px-4 py-3 whitespace-nowrap">
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
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-secondary">
                        {member.email}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <StatusBadge
                          status={member.role}
                          variant={member.role === 'admin' ? 'warning' : member.role === 'super_admin' ? 'error' : 'default'}
                        />
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <StatusBadge
                          status={member.is_active !== false ? 'active' : 'inactive'}
                          variant={member.is_active !== false ? 'success' : 'default'}
                        />
                      </td>
                      {canManageUsers && (
                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                          <div className="flex justify-end gap-2">
                            {canEdit && (
                              <ActionButton variant="change" onClick={() => handleEditUser(member)}>
                                Edit
                              </ActionButton>
                            )}
                            {canRemove && (
                              <ActionButton
                                variant="destructive"
                                onClick={() => handleRemoveMember(member.id, member.username)}
                              >
                                Remove
                              </ActionButton>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          )}
        </div>

        {/* Pagination Controls - Bottom */}
        {paginatedMembers.length > 0 && (
          <div className="px-4 py-4 border-t border-primary">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalCount={totalCount}
              pageSize={pageSize}
              onPageChange={setCurrentPage}
              itemLabel="member"
              position="bottom"
            />
          </div>
        )}
      </div>

      {/* Invite User Modal */}
      <Modal isOpen={showInviteModal} onClose={() => { setShowInviteModal(false); setInviteError(null); }} title="Invite User to Organization" size="md">
        <form onSubmit={handleInviteUser}>
          <div className="p-4 space-y-4">
            {inviteError && (
              <div className="alert alert-error">
                <p className="text-sm text-danger">{inviteError}</p>
              </div>
            )}

            <div>
              <label htmlFor="email" className="form-label">
                Email Address *
              </label>
              <input
                type="email"
                id="email"
                required
                value={inviteForm.email}
                onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
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
                onChange={(e) => setInviteForm({ ...inviteForm, username: e.target.value })}
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
                  onChange={(e) => setInviteForm({ ...inviteForm, first_name: e.target.value })}
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
                  onChange={(e) => setInviteForm({ ...inviteForm, last_name: e.target.value })}
                  className="form-input"
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="form-label">
                Temporary Password *
              </label>
              <input
                type="password"
                id="password"
                required
                value={inviteForm.password}
                onChange={(e) => setInviteForm({ ...inviteForm, password: e.target.value })}
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
                value={inviteForm.confirmPassword}
                onChange={(e) => setInviteForm({ ...inviteForm, confirmPassword: e.target.value })}
                className="form-input"
                placeholder="Re-enter password"
              />
              <p className="mt-1 text-xs text-secondary">
                User should change this password on first login
              </p>
            </div>

            <div>
              <label htmlFor="role" className="form-label">
                Role *
              </label>
              <select
                id="role"
                value={inviteForm.role}
                onChange={(e) => setInviteForm({ ...inviteForm, role: e.target.value as 'user' | 'admin' | 'super_admin' })}
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
              Invite User
            </button>
            <button
              type="button"
              onClick={() => {
                setShowInviteModal(false);
                setInviteError(null);
                setInviteForm({ email: '', username: '', first_name: '', last_name: '', password: '', confirmPassword: '', role: 'user' });
              }}
              className="mt-3 w-full inline-flex justify-center rounded-md border border-primary shadow-sm px-4 py-2 bg-card text-base font-medium text-secondary hover:bg-surface focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
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
                  onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
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
                  onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
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
                onChange={(e) => setEditForm({ ...editForm, username: e.target.value })}
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
                onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                className="form-input"
              />
            </div>

            {(() => {
              // Super admins cannot have their role changed via org management
              // They are a platform-level concept, not an org-level one
              const isEditingSuperAdmin = editingUser?.role === 'super_admin';
              const canChangeRole = !isEditingSuperAdmin;
              const canChangeStatus = !isEditingSuperAdmin;

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
                        onChange={(e) => setEditForm({ ...editForm, role: e.target.value as 'user' | 'admin' })}
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
                      onChange={(e) => setEditForm({ ...editForm, is_active: e.target.value === 'active' })}
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
              {editSaving ? 'Saving...' : 'Save Changes'}
            </button>
            <button
              type="button"
              onClick={() => {
                setEditingUser(null);
                setEditError(null);
              }}
              className="mt-3 w-full inline-flex justify-center rounded-md border border-primary shadow-sm px-4 py-2 bg-card text-base font-medium text-secondary hover:bg-surface focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}
