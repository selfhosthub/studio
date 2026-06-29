// ui/app/settings/profile/page.tsx

'use client';

import { useUser } from '@/entities/user';
import { updateCurrentUserProfile, uploadUserAvatar, deleteUserAvatar } from '@/shared/api';
import { UserAvatar } from '@/shared/ui';
import { useToast } from '@/features/toast';
import { useRef, useState } from 'react';

const AVATAR_ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const AVATAR_MAX_BYTES = 5 * 1024 * 1024; // 5MB

export default function ProfilePage() {
  const { user, refreshUser } = useUser();
  const { toast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const [isRemovingAvatar, setIsRemovingAvatar] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Controlled form state
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
  });

  // Seed form data from user context during render when user data changes (Pattern C).
  // prevUserKey starts as null so the first non-null userKey always seeds the form,
  // even when `user` is already loaded on first render.
  const userKey = user ? `${user.id}|${user.first_name}|${user.last_name}|${user.email}` : null;
  const [prevUserKey, setPrevUserKey] = useState<string | null>(null);
  if (userKey !== prevUserKey) {
    setPrevUserKey(userKey);
    if (user) {
      setFormData({
        first_name: user.first_name || '',
        last_name: user.last_name || '',
        email: user.email || '',
      });
    }
  }

  // Handle form field changes
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  // Open the hidden file picker when the Change button is clicked
  const handleAvatarButtonClick = () => {
    fileInputRef.current?.click();
  };

  // Validate and upload the selected avatar file
  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Reset the input so selecting the same file again re-triggers onChange
    e.target.value = '';
    if (!file || !user) {
      return;
    }

    if (!AVATAR_ALLOWED_TYPES.includes(file.type)) {
      toast({ title: 'Unsupported image type', description: 'Use JPEG, PNG, GIF, or WebP.', variant: 'destructive' });
      return;
    }
    if (file.size > AVATAR_MAX_BYTES) {
      toast({ title: 'Image too large', description: 'Maximum size is 5MB.', variant: 'destructive' });
      return;
    }

    try {
      setIsUploadingAvatar(true);
      await uploadUserAvatar(user.id, file);
      toast({ title: 'Profile photo updated', variant: 'success' });
      if (refreshUser) {
        await refreshUser();
      }
    } catch (err) {
      console.error('Failed to upload avatar:', err);
      toast({ title: 'Failed to update profile photo', description: err instanceof Error ? err.message : undefined, variant: 'destructive' });
    } finally {
      setIsUploadingAvatar(false);
    }
  };

  // Remove the current avatar
  const handleRemoveAvatar = async () => {
    if (!user) {
      return;
    }
    try {
      setIsRemovingAvatar(true);
      await deleteUserAvatar(user.id);
      toast({ title: 'Profile photo removed', variant: 'success' });
      if (refreshUser) {
        await refreshUser();
      }
    } catch (err) {
      console.error('Failed to remove avatar:', err);
      toast({ title: 'Failed to remove profile photo', description: err instanceof Error ? err.message : undefined, variant: 'destructive' });
    } finally {
      setIsRemovingAvatar(false);
    }
  };

  // Handle profile form submission
  const handleProfileSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    e.stopPropagation();

    try {
      setIsSubmitting(true);
      await updateCurrentUserProfile({
        first_name: formData.first_name || undefined,
        last_name: formData.last_name || undefined,
        email: formData.email || undefined,
      });

      toast({ title: 'Profile updated successfully', variant: 'success' });
      // Refresh user data to sync context with backend
      if (refreshUser) {
        await refreshUser();
      }
    } catch (err) {
      console.error('Failed to update profile:', err);
      toast({ title: 'Failed to update profile', description: err instanceof Error ? err.message : undefined, variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }

    return false;
  };

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="md:grid md:grid-cols-3 md:gap-6">
          <div className="md:col-span-1">
            <h3 className="text-lg font-medium leading-6 text-primary">
              Profile Information
            </h3>
            <p className="mt-1 text-muted">
              Update your personal information.
            </p>
          </div>
          <div className="mt-5 md:mt-0 md:col-span-2">
            <form onSubmit={handleProfileSubmit} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="first_name" className="form-label">
                    First Name
                  </label>
                  <input
                    type="text"
                    name="first_name"
                    id="first_name"
                    value={formData.first_name}
                    onChange={handleChange}
                    className="form-input"
                  />
                </div>
                <div>
                  <label htmlFor="last_name" className="form-label">
                    Last Name
                  </label>
                  <input
                    type="text"
                    name="last_name"
                    id="last_name"
                    value={formData.last_name}
                    onChange={handleChange}
                    className="form-input"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="email" className="form-label">
                  Email
                </label>
                <input
                  type="email"
                  name="email"
                  id="email"
                  value={formData.email}
                  onChange={handleChange}
                  className="form-input"
                />
              </div>
              <div>
                <label htmlFor="avatar" className="form-label">
                  Profile Photo
                </label>
                <div className="mt-2 flex items-center">
                  <UserAvatar user={user} sizeClassName="h-12 w-12" textClassName="text-lg" />
                  <input
                    ref={fileInputRef}
                    type="file"
                    id="avatar"
                    accept="image/jpeg,image/png,image/gif,image/webp"
                    onChange={handleAvatarChange}
                    className="hidden"
                  />
                  <button
                    type="button"
                    onClick={handleAvatarButtonClick}
                    disabled={isUploadingAvatar || isRemovingAvatar}
                    className="btn-secondary ml-5"
                  >
                    {isUploadingAvatar ? 'Uploading...' : 'Change'}
                  </button>
                  {user?.avatar_url && (
                    <button
                      type="button"
                      onClick={handleRemoveAvatar}
                      disabled={isUploadingAvatar || isRemovingAvatar}
                      className="btn-secondary ml-3"
                    >
                      {isRemovingAvatar ? 'Removing...' : 'Remove'}
                    </button>
                  )}
                </div>
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="btn-primary ml-3"
                >
                  {isSubmitting ? 'Saving...' : 'Save'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
