// ui/app/settings/profile/page.tsx

'use client';

import { useUser } from '@/entities/user';
import { updateCurrentUserProfile } from '@/shared/api';
import { useToast } from '@/features/toast';
import { useState, useEffect } from 'react';

export default function ProfilePage() {
  const { user, refreshUser } = useUser();
  const { toast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Controlled form state
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
  });

  // Sync form data with user context
  useEffect(() => {
    if (user) {
      setFormData({
        first_name: user.first_name || '',
        last_name: user.last_name || '',
        email: user.email || '',
      });
    }
  }, [user]);

  // Handle form field changes
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
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
                  <span className="h-12 w-12 rounded-full overflow-hidden bg-card">
                    {user?.avatar_url ? (
                      // eslint-disable-next-line @next/next/no-img-element -- external avatar URL
                      <img src={user.avatar_url} alt="User avatar" className="h-full w-full" />
                    ) : (
                      <svg className="h-full w-full text-muted" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M24 20.993V24H0v-2.996A14.977 14.977 0 0112.004 15c4.904 0 9.26 2.354 11.996 5.993zM16.002 8.999a4 4 0 11-8 0 4 4 0 018 0z" />
                      </svg>
                    )}
                  </span>
                  <button
                    type="button"
                    className="btn-secondary ml-5"
                  >
                    Change
                  </button>
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
