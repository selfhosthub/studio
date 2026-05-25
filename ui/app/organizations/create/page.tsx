// ui/app/organizations/create/page.tsx

"use client";

import React, { useState } from "react";
import { DashboardLayout } from "@/widgets/layout";
import { useRouter } from "next/navigation";
import { createOrganization, createAndInviteUser } from "@/shared/api";
import { useUser } from "@/entities/user";
import { useRoleAccess } from "@/features/roles";
import { useToast } from "@/features/toast";

export default function CreateOrganizationPage() {
  // Restrict access to super_admin only
  const { hasAccess, isLoading: authLoading } = useRoleAccess(['super_admin']);
  const router = useRouter();
  const { user } = useUser();
  const { toast } = useToast();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [organizationForm, setOrganizationForm] = useState({
    name: '',
    slug: '',
    description: '',
  });

  const [adminForm, setAdminForm] = useState({
    email: '',
    username: '',
    password: '',
    first_name: '',
    last_name: '',
  });

  const [createAdminUser, setCreateAdminUser] = useState(true);

  // Auto-generate slug from name
  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const name = e.target.value;
    const slug = name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '');

    setOrganizationForm({
      ...organizationForm,
      name,
      slug,
    });
  };

  const handleOrgFieldChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setOrganizationForm({
      ...organizationForm,
      [name]: value,
    });
  };

  const handleAdminFieldChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setAdminForm({
      ...adminForm,
      [name]: value,
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError(null);

    try {
      // Validate required fields
      if (!organizationForm.name.trim()) {
        throw new Error('Organization name is required');
      }
      if (!organizationForm.slug.trim()) {
        throw new Error('Organization slug is required');
      }

      if (createAdminUser) {
        if (!adminForm.email.trim()) {
          throw new Error('Admin email is required');
        }
        if (!adminForm.username.trim()) {
          throw new Error('Admin username is required');
        }
        if (!adminForm.password.trim()) {
          throw new Error('Admin password is required');
        }
      }

      // Create organization
      const newOrg = await createOrganization({
        name: organizationForm.name,
        slug: organizationForm.slug,
        description: organizationForm.description || null,
      });

      // Create admin user if requested
      if (createAdminUser) {
        await createAndInviteUser(
          newOrg.id,
          adminForm.email,
          adminForm.password,
          'admin',
          adminForm.username
        );
      }

      toast({ title: 'Organization created', description: 'Organization created successfully!', variant: 'success' });
      router.push(`/organizations/${newOrg.id}`);
    } catch (err: unknown) {
      let errorMessage = 'Failed to create organization';
      if (err instanceof Error) {
        errorMessage = err.message;
      } else if (typeof err === 'string') {
        errorMessage = err;
      } else if (typeof err === 'object' && err !== null && 'detail' in err) {
        errorMessage = String((err as { detail: string }).detail);
      }

      setError(errorMessage);
      setCreating(false);
    }
  };

  // Show loading state while checking access
  if (authLoading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted">Loading...</div>
        </div>
      </DashboardLayout>
    );
  }

  // Show access denied if user doesn't have permission
  if (!hasAccess) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <h2 className="text-xl font-semibold text-danger mb-2">Access Denied</h2>
            <p className="text-secondary">
              You do not have permission to create organizations. Only administrators can access this page.
            </p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="px-4 py-6 sm:px-6 lg:px-8 max-w-4xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-primary">
            Create Organization
          </h1>
          <p className="mt-2 text-sm text-secondary">
            Create a new organization and optionally add an admin user
          </p>
        </div>

        {error && (
          <div className="mb-6 alert alert-error">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-danger" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm">{error}</p>
              </div>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Organization Details Section */}
          <div className="card">
            <h2 className="text-lg font-medium text-primary mb-4">
              Details
            </h2>
            <div className="space-y-4">
              <div>
                <label htmlFor="name" className="form-label">
                  Organization Name *
                </label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  required
                  value={organizationForm.name}
                  onChange={handleNameChange}
                  className="form-input"
                  placeholder="e.g., Acme Corporation"
                />
                <p className="form-helper">
                  The display name for your organization
                </p>
              </div>

              <div>
                <label htmlFor="slug" className="form-label">
                  Organization Slug *
                </label>
                <input
                  type="text"
                  id="slug"
                  name="slug"
                  required
                  value={organizationForm.slug}
                  onChange={handleOrgFieldChange}
                  pattern="[a-z0-9-]+"
                  className="form-input-mono"
                  placeholder="e.g., acme-corp"
                />
                <p className="form-helper">
                  Unique identifier (lowercase letters, numbers, and hyphens only)
                </p>
              </div>

              <div>
                <label htmlFor="description" className="form-label">
                  Description
                </label>
                <textarea
                  id="description"
                  name="description"
                  rows={3}
                  value={organizationForm.description}
                  onChange={handleOrgFieldChange}
                  className="form-textarea"
                  placeholder="Optional description of the organization"
                />
              </div>
            </div>
          </div>

          {/* Admin User Section */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-primary">
                Admin User (Optional)
              </h2>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={createAdminUser}
                  onChange={(e) => setCreateAdminUser(e.target.checked)}
                  className="rounded border-primary text-info focus:ring-blue-500"
                />
                <span className="text-sm text-secondary">Create admin user</span>
              </label>
            </div>

            {createAdminUser && (
              <div className="space-y-4">
                <div className="alert alert-info">
                  <p className="text-sm">
                    Creating an admin user is recommended. Organizations need at least one admin to be functional.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="admin_email" className="form-label">
                      Email *
                    </label>
                    <input
                      type="email"
                      id="admin_email"
                      name="email"
                      required={createAdminUser}
                      value={adminForm.email}
                      onChange={handleAdminFieldChange}
                      className="form-input"
                      placeholder="admin@example.com"
                    />
                  </div>

                  <div>
                    <label htmlFor="admin_username" className="form-label">
                      Username *
                    </label>
                    <input
                      type="text"
                      id="admin_username"
                      name="username"
                      required={createAdminUser}
                      value={adminForm.username}
                      onChange={handleAdminFieldChange}
                      className="form-input"
                      placeholder="admin"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="admin_password" className="form-label">
                    Password *
                  </label>
                  <input
                    type="password"
                    id="admin_password"
                    name="password"
                    required={createAdminUser}
                    value={adminForm.password}
                    onChange={handleAdminFieldChange}
                    className="form-input"
                    placeholder="Secure password"
                  />
                  <p className="form-helper">
                    Minimum 8 characters recommended
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="admin_first_name" className="form-label">
                      First Name
                    </label>
                    <input
                      type="text"
                      id="admin_first_name"
                      name="first_name"
                      value={adminForm.first_name}
                      onChange={handleAdminFieldChange}
                      className="form-input"
                      placeholder="Optional"
                    />
                  </div>

                  <div>
                    <label htmlFor="admin_last_name" className="form-label">
                      Last Name
                    </label>
                    <input
                      type="text"
                      id="admin_last_name"
                      name="last_name"
                      value={adminForm.last_name}
                      onChange={handleAdminFieldChange}
                      className="form-input"
                      placeholder="Optional"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Form Actions */}
          <div className="flex items-center justify-end space-x-4">
            <button
              type="button"
              onClick={() => router.push('/organizations/list')}
              disabled={creating}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={creating}
              className="btn-primary"
            >
              {creating ? 'Creating...' : 'Create Organization'}
            </button>
          </div>
        </form>
      </div>
    </DashboardLayout>
  );
}
