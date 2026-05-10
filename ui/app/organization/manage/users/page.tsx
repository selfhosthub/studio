// ui/app/organization/manage/users/page.tsx

'use client';

import {
  ActionButton,
  StatusBadge,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
  Modal,
} from "@/shared/ui";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { PAGINATION } from '@/shared/lib/constants';
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

/**
 * Organization Users page - manages users in the admin's own organization.
 * Uses the same functionality as /organizations/[id]/users but stays within
 * the /organization/manage/ layout for consistent tab navigation.
 */
export default function OrganizationUsersPage() {
  const router = useRouter();
  const { user } = useUser();
  const { toast } = useToast();
  const orgId = user?.org_id || '';

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

    setLoading(true);
    getOrganizationMembers(orgId)
      .then((data) => {
        setMembers(data);
        setError(null);
      })
      .catch((err) => {
        console.error('Failed to fetch organization members:', err);
        setError(err instanceof Error ? err.message : 'Failed to load organization members');
      })
      .finally(() => setLoading(false));
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

  // Pagination
  const totalPages = Math.ceil(filteredMembers.length / pageSize);
  const paginatedMembers = filteredMembers.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  // Reset to page 1 when search changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm]);

  const handleRemoveMember = async (memberId: string, memberName: string) => {
    if (!confirm(`Are you sure you want to remove ${memberName} from the organization?`)) {
      return;
    }

    try {
      await removeOrganizationMember(orgId, memberId);
      setMembers(members.filter(m => m.id !== memberId));
    } catch (err: unknown) {
      toast({ title: 'Remove failed', description: err instanceof Error ? err.message : 'Failed to remove member', variant: 'destructive' });
    }
  };

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
    } catch (err: unknown) {
      setInviteError(err instanceof Error ? err.message : 'Failed to invite user');
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

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;

    setEditSaving(true);
    setEditError(null);

    try {
      const updatedUser = await updateUserAsAdmin(editingUser.id, editForm);
      setMembers(members.map(m => m.id === editingUser.id ? { ...m, ...updatedUser } : m));
      setEditingUser(null);
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : 'Failed to update user');
    } finally {
      setEditSaving(false);
    }
  };

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
            <h2 className="text-lg font-semibold text-primary">Members ({members.length})</h2>
            <p className="text-sm text-secondary">Manage organization members</p>
          </div>
        </div>
        {canManageUsers && (
          <ActionButton variant="active" onClick={() => setShowInviteModal(true)}>
            Add User
          </ActionButton>
        )}
      </div>

      {loading && <LoadingState message="Loading members..." />}

      {!loading && error && (
        <ErrorState
          title="Error Loading Members"
          message={error}
          onRetry={() => window.location.reload()}
        />
      )}

      {!loading && !error && (
        <>
          {/* Search */}
          <SearchInput
            value={searchTerm}
            onChange={setSearchTerm}
            placeholder="Search members..."
          />

          {/* Members Table */}
          {paginatedMembers.length > 0 ? (
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
                  {paginatedMembers.map((member) => (
                    <tr key={member.id}>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex items-center">
                          <div className="w-8 h-8 rounded-full bg-input flex items-center justify-center text-sm font-medium text-secondary">
                            {member.first_name?.[0] || member.username?.[0] || '?'}
                          </div>
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
                            <ActionButton variant="change" onClick={() => handleEditClick(member)}>
                              Edit
                            </ActionButton>
                            {member.id !== user?.id && (
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
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No members found"
              description={searchTerm ? 'No members match your search' : 'No members in this organization'}
            />
          )}

          {/* Pagination */}
          {filteredMembers.length > pageSize && (
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalCount={filteredMembers.length}
              pageSize={pageSize}
              onPageChange={setCurrentPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setCurrentPage(1);
              }}
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              itemLabel="member"
              position="bottom"
            />
          )}
        </>
      )}

      {/* Invite Modal */}
      <Modal isOpen={showInviteModal} onClose={() => setShowInviteModal(false)} title="Add New User" size="sm">
        <form onSubmit={handleInviteSubmit} className="p-4 space-y-4">
          <div>
            <label htmlFor="create-user-email" className="block text-sm font-medium text-secondary mb-1">Email</label>
            <input
              id="create-user-email"
              type="email"
              required
              value={inviteForm.email}
              onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
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
              onChange={(e) => setInviteForm({ ...inviteForm, username: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="create-user-password" className="block text-sm font-medium text-secondary mb-1">Password</label>
            <input
              id="create-user-password"
              type="password"
              required
              value={inviteForm.password}
              onChange={(e) => setInviteForm({ ...inviteForm, password: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="create-user-confirm-password" className="block text-sm font-medium text-secondary mb-1">Confirm Password</label>
            <input
              id="create-user-confirm-password"
              type="password"
              required
              value={inviteForm.confirmPassword}
              onChange={(e) => setInviteForm({ ...inviteForm, confirmPassword: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="create-user-role" className="block text-sm font-medium text-secondary mb-1">Role</label>
            <select
              id="create-user-role"
              value={inviteForm.role}
              onChange={(e) => setInviteForm({ ...inviteForm, role: e.target.value as 'user' | 'admin' | 'super_admin' })}
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
            <ActionButton variant="warning" onClick={() => setShowInviteModal(false)}>
              Cancel
            </ActionButton>
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
              onChange={(e) => setEditForm({ ...editForm, username: e.target.value })}
              className="form-input w-full"
            />
          </div>
          <div>
            <label htmlFor="edit-user-email" className="block text-sm font-medium text-secondary mb-1">Email</label>
            <input
              id="edit-user-email"
              type="email"
              value={editForm.email}
              onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
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
                onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
                className="form-input w-full"
              />
            </div>
            <div>
              <label htmlFor="edit-user-last-name" className="block text-sm font-medium text-secondary mb-1">Last Name</label>
              <input
                id="edit-user-last-name"
                type="text"
                value={editForm.last_name}
                onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
                className="form-input w-full"
              />
            </div>
          </div>
          <div>
            <label htmlFor="edit-user-role" className="block text-sm font-medium text-secondary mb-1">Role</label>
            <select
              id="edit-user-role"
              value={editForm.role}
              onChange={(e) => setEditForm({ ...editForm, role: e.target.value as 'user' | 'admin' | 'super_admin' })}
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
              onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
              className="form-checkbox"
            />
            <label htmlFor="is_active" className="text-sm text-secondary">Active</label>
          </div>
          {editError && (
            <div className="text-sm text-danger">{editError}</div>
          )}
          <div className="flex justify-end gap-2">
            <ActionButton variant="warning" onClick={() => setEditingUser(null)} disabled={editSaving}>
              Cancel
            </ActionButton>
            <button type="submit" className="btn-primary" disabled={editSaving}>
              {editSaving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
