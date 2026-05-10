// ui/app/organizations/[id]/page.tsx

"use client";

import { Building2 } from "lucide-react";
import {
  ActionButton,
  StatusBadge,
} from "@/shared/ui";
import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  getOrganization,
  updateOrganization,
} from "@/shared/api";
import { useUser } from "@/entities/user";
import { useToast } from "@/features/toast";

export default function OrganizationDetailsPage() {
  const router = useRouter();
  const params = useParams();
  const { user } = useUser();
  const { toast } = useToast();
  const orgId = params.id as string;

  const [organization, setOrganization] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    shortName: '',
    tagline: '',
    notes: '',
  });

  // Check permissions
  const isSuperAdmin = user?.role === 'super_admin';
  const isViewingOtherOrg = isSuperAdmin && user?.org_id !== orgId;

  // Super-admin can view other orgs but cannot edit them (only admins can edit their own org)
  const canEdit = (user?.role === 'admin' || user?.role === 'super_admin') && user?.org_id === orgId;
  const canView = isSuperAdmin || user?.org_id === orgId;
  // System org cannot be deactivated
  const isSystemOrg = organization?.slug === 'system';

  // Redirect if user doesn't have access
  useEffect(() => {
    if (user && !canView) {
      router.push('/dashboard');
    }
  }, [user, canView, router]);

  // Fetch organization
  useEffect(() => {
    if (!user) return;
    if (!canView) return;

    getOrganization(orgId)
      .then((orgData) => {
        setOrganization(orgData);
        setFormData({
          name: orgData.name || '',
          shortName: orgData.settings?.branding?.short_name || '',
          tagline: orgData.settings?.branding?.tagline || '',
          notes: orgData.description || '',
        });
        setError(null);
      })
      .catch((err) => {
        // Show actual error message from backend for debugging
        const errorMessage = err instanceof Error ? err.message :
          (err?.detail || err?.message || 'Failed to load organization');
        setError(errorMessage);
      })
      .finally(() => setLoading(false));
  }, [orgId, canView, user]);

  // Handle form field changes
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  // Handle organization update
  const handleSaveOrganization = async () => {
    setIsSaving(true);
    try {
      // Build updates - merge branding fields into existing settings
      const updates: any = {};

      if (formData.name !== organization.name) {
        updates.name = formData.name;
      }
      if (formData.notes !== (organization.description || '')) {
        updates.description = formData.notes || undefined;
      }

      // Check if branding fields changed
      const currentShortName = organization.settings?.branding?.short_name || '';
      const currentTagline = organization.settings?.branding?.tagline || '';

      if (formData.shortName !== currentShortName || formData.tagline !== currentTagline) {
        // Merge into existing settings, preserving colors, logo, etc.
        updates.settings = {
          ...organization.settings,
          branding: {
            ...organization.settings?.branding,
            short_name: formData.shortName || undefined,
            tagline: formData.tagline || undefined,
          }
        };
      }

      if (Object.keys(updates).length === 0) {
        setIsEditing(false);
        setIsSaving(false);
        return;
      }

      const updated = await updateOrganization(orgId, updates);
      setOrganization(updated);
      setFormData({
        name: updated.name || '',
        shortName: updated.settings?.branding?.short_name || '',
        tagline: updated.settings?.branding?.tagline || '',
        notes: updated.description || '',
      });
      setIsEditing(false);
    } catch (err: unknown) {
      toast({ title: 'Update failed', description: err instanceof Error ? err.message : 'Failed to update organization', variant: 'destructive' });
    } finally {
      setIsSaving(false);
    }
  };

  // Handle cancel editing
  const handleCancelEdit = () => {
    setFormData({
      name: organization.name || '',
      shortName: organization.settings?.branding?.short_name || '',
      tagline: organization.settings?.branding?.tagline || '',
      notes: organization.description || '',
    });
    setIsEditing(false);
  };

  // Handle organization activate/deactivate (super_admin only)
  const handleToggleActive = async () => {
    const newStatus = !organization.is_active;
    const action = newStatus ? 'activate' : 'deactivate';

    if (!confirm(`Are you sure you want to ${action} this organization?`)) {
      return;
    }

    try {
      const updated = await updateOrganization(orgId, { is_active: newStatus });
      setOrganization(updated);
      toast({ title: `Organization ${action}d`, variant: 'success' });
    } catch (err: unknown) {
      toast({ title: `Failed to ${action} organization`, description: err instanceof Error ? err.message : undefined, variant: 'destructive' });
    }
  };

  if (!canView) {
    return null;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="spinner-md"></div>
          <p className="mt-2 text-sm text-secondary">Loading organization...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card bg-danger-subtle border-danger">
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg className="h-5 w-5 text-danger" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-danger">Error Loading Organization</h3>
            <p className="mt-1 text-sm text-danger">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!organization) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Organization Information Card */}
      <div className="bg-card rounded-lg shadow-md p-6 border border-primary">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center">
            <div className="w-10 h-10 bg-info-subtle rounded-lg flex items-center justify-center mr-3">
              <Building2 className="w-5 h-5 text-info" />
            </div>
            <h2 className="text-xl font-bold text-primary">
              Organization Information
            </h2>
          </div>
          {canEdit && !isEditing && (
            <ActionButton variant="change" onClick={() => setIsEditing(true)}>
              Edit
            </ActionButton>
          )}
          {canEdit && isEditing && (
            <div className="flex space-x-2">
              <ActionButton variant="active" onClick={handleSaveOrganization} disabled={isSaving}>
                {isSaving ? 'Saving...' : 'Save'}
              </ActionButton>
              <ActionButton variant="warning" onClick={handleCancelEdit} disabled={isSaving}>
                Cancel
              </ActionButton>
            </div>
          )}
        </div>

        <div className="space-y-4">
          {/* Name */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-secondary mb-2">
              Organization Name *
            </label>
            {isEditing ? (
              <input
                type="text"
                id="name"
                name="name"
                value={formData.name}
                onChange={handleChange}
                required
                className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Acme Corp"
              />
            ) : (
              <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary">
                {organization.name}
              </p>
            )}
            <p className="text-sm text-secondary mt-1">
              Your organization&apos;s name displayed throughout the platform
            </p>
          </div>

          {/* Slug (read-only) */}
          <div>
            <p className="block text-sm font-medium text-secondary mb-2">
              Slug
            </p>
            <p className="px-4 py-2 bg-surface rounded-md text-primary font-mono text-sm border border-primary">
              {organization.slug}
            </p>
            <p className="text-sm text-secondary mt-1">
              URL-safe identifier (cannot be changed)
            </p>
          </div>

          {/* Short Name */}
          <div>
            <label htmlFor="shortName" className="block text-sm font-medium text-secondary mb-2">
              Short Name
            </label>
            {isEditing ? (
              <input
                type="text"
                id="shortName"
                name="shortName"
                value={formData.shortName}
                onChange={handleChange}
                className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Acme"
              />
            ) : (
              <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary">
                {organization.settings?.branding?.short_name || '-'}
              </p>
            )}
            <p className="text-sm text-secondary mt-1">
              Abbreviated name for compact spaces (e.g., mobile menu)
            </p>
          </div>

          {/* Tagline */}
          <div>
            <label htmlFor="tagline" className="block text-sm font-medium text-secondary mb-2">
              Tagline
            </label>
            {isEditing ? (
              <input
                type="text"
                id="tagline"
                name="tagline"
                value={formData.tagline}
                onChange={handleChange}
                className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Streamline Your Media Production"
              />
            ) : (
              <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary">
                {organization.settings?.branding?.tagline || '-'}
              </p>
            )}
            <p className="text-sm text-secondary mt-1">
              Brief description or slogan shown in headers and footers
            </p>
          </div>

          {/* Notes (formerly Description) */}
          <div>
            <label htmlFor="notes" className="block text-sm font-medium text-secondary mb-2">
              Notes
            </label>
            {isEditing ? (
              <textarea
                id="notes"
                name="notes"
                value={formData.notes}
                onChange={handleChange}
                rows={3}
                className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Internal notes about this organization..."
              />
            ) : (
              <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary min-h-[60px]">
                {organization.description || '-'}
              </p>
            )}
            <p className="text-sm text-secondary mt-1">
              Internal notes (not displayed publicly)
            </p>
          </div>

          {/* Status */}
          <div>
            <p className="block text-sm font-medium text-secondary mb-2">
              Status
            </p>
            <div className="flex items-center space-x-3 px-4 py-2 bg-card rounded-md border border-primary">
              <StatusBadge
                status={organization.is_active ? 'active' : 'inactive'}
                variant={organization.is_active ? 'success' : 'default'}
              />
              {isSuperAdmin && !isSystemOrg && (
                <ActionButton
                  variant={organization.is_active ? 'warning' : 'active'}
                  onClick={handleToggleActive}
                >
                  {organization.is_active ? 'Deactivate' : 'Activate'}
                </ActionButton>
              )}
            </div>
          </div>

          {/* Created */}
          <div>
            <p className="block text-sm font-medium text-secondary mb-2">
              Created
            </p>
            <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary">
              {organization.created_at ? new Date(organization.created_at).toLocaleDateString() : 'N/A'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
