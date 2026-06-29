// ui/app/organization/manage/details/page.tsx

'use client';

import { Building2 } from 'lucide-react';
import { useState, useEffect } from 'react';
import { getOrganization, updateOrganization } from '@/shared/api';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';

export default function OrganizationDetailsPage() {
  const { user } = useUser();
  const { toast } = useToast();
  const [organization, setOrganization] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit mode state
  const [editMode, setEditMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    shortName: '',
    tagline: '',
    notes: '',
  });

  useEffect(() => {
    async function fetchOrganization() {
      if (!user?.org_id) return;

      try {
        setLoading(true);
        const org = await getOrganization(user.org_id);
        setOrganization(org);
        setFormData({
          name: org.name || '',
          shortName: org.settings?.branding?.short_name || '',
          tagline: org.settings?.branding?.tagline || '',
          notes: org.description || '',
        });
        setError(null);
      } catch (err) {
        console.error('Failed to fetch organization:', err);
        setError(err instanceof Error ? err.message : 'Failed to load organization');
      } finally {
        setLoading(false);
      }
    }

    fetchOrganization();
  }, [user?.org_id]);

  const handleEdit = () => {
    setEditMode(true);
    setError(null);
  };

  const handleCancel = () => {
    setEditMode(false);
    setError(null);
    // Reset form to original data
    if (organization) {
      setFormData({
        name: organization.name || '',
        shortName: organization.settings?.branding?.short_name || '',
        tagline: organization.settings?.branding?.tagline || '',
        notes: organization.description || '',
      });
    }
  };

  const handleSave = async () => {
    if (!user?.org_id) return;

    if (!formData.name.trim()) {
      setError('Organization name is required');
      return;
    }

    try {
      setSaving(true);
      setError(null);

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
        setEditMode(false);
        return;
      }

      const updated = await updateOrganization(user.org_id, updates);
      setOrganization(updated);
      setFormData({
        name: updated.name || '',
        shortName: updated.settings?.branding?.short_name || '',
        tagline: updated.settings?.branding?.tagline || '',
        notes: updated.description || '',
      });
      setEditMode(false);
      toast({ title: 'Organization updated successfully', variant: 'success' });
    } catch (err) {
      console.error('Failed to update organization:', err);
      setError(err instanceof Error ? err.message : 'Failed to update organization');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="spinner-lg"></div>
      </div>
    );
  }

  if (error && !organization) {
    return (
      <div className="alert alert-error">
        <p className="text-danger">{error || 'Organization not found'}</p>
      </div>
    );
  }

  if (!organization) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Error Message */}
      {error && (
        <div className="p-3 bg-danger-subtle border border-danger rounded-md">
          <p className="text-sm text-danger">{error}</p>
        </div>
      )}

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
          {!editMode ? (
            <button
              onClick={handleEdit}
              className="btn-primary"
            >
              Edit
            </button>
          ) : (
            <div className="flex space-x-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="py-2 px-4 bg-success hover:bg-success text-white font-medium rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={handleCancel}
                disabled={saving}
                className="py-2 px-4 border border-primary text-secondary font-medium rounded-md shadow-sm hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2"
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        <div className="space-y-4">
          {/* Name */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-secondary mb-2">
              Organization Name *
            </label>
            {editMode ? (
              <input
                type="text"
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Acme Corp"
              />
            ) : (
              <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary">{organization.name}</p>
            )}
            <p className="text-sm text-secondary mt-1">
              Your organization&apos;s name displayed throughout the platform
            </p>
          </div>

          {/* Slug (read-only) */}
          <div>
            <label className="block text-sm font-medium text-secondary mb-2">
              Slug
            </label>
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
            {editMode ? (
              <input
                type="text"
                id="shortName"
                value={formData.shortName}
                onChange={(e) => setFormData({ ...formData, shortName: e.target.value })}
                className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Acme"
              />
            ) : (
              <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary">{organization.settings?.branding?.short_name || '-'}</p>
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
            {editMode ? (
              <input
                type="text"
                id="tagline"
                value={formData.tagline}
                onChange={(e) => setFormData({ ...formData, tagline: e.target.value })}
                className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Streamline Your Media Production"
              />
            ) : (
              <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary">{organization.settings?.branding?.tagline || '-'}</p>
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
            {editMode ? (
              <textarea
                id="notes"
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                rows={3}
                className="w-full px-4 py-2 rounded-md border border-primary bg-card text-primary focus:border-info focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Internal notes about this organization..."
              />
            ) : (
              <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary min-h-[60px]">{organization.description || '-'}</p>
            )}
            <p className="text-sm text-secondary mt-1">
              Internal notes (not displayed publicly)
            </p>
          </div>

          {/* Status */}
          <div>
            <label className="block text-sm font-medium text-secondary mb-2">
              Status
            </label>
            <div className="px-4 py-2 bg-card rounded-md border border-primary">
              <span className={`inline-flex rounded-full px-2 text-xs font-semibold leading-5 ${
                organization.is_active
                  ? 'bg-success-subtle text-success'
                  : 'bg-danger-subtle text-danger'
              }`}>
                {organization.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>
          </div>

          {/* Created */}
          <div>
            <label className="block text-sm font-medium text-secondary mb-2">
              Created
            </label>
            <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary">
              {new Date(organization.created_at).toLocaleDateString()}
            </p>
          </div>

          {/* Last Updated */}
          <div>
            <label className="block text-sm font-medium text-secondary mb-2">
              Last Updated
            </label>
            <p className="px-4 py-2 bg-card rounded-md text-primary border border-primary">
              {new Date(organization.updated_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
