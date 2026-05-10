// ui/app/settings/account/page.tsx

'use client';

import { changePassword } from '@/shared/api';
import { useToast } from '@/features/toast';
import { useState } from 'react';

export default function AccountPage() {
  const { toast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Handle password form submission
  const handlePasswordSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    e.stopPropagation();

    // Capture form reference before async operation (e.currentTarget becomes null after await)
    const form = e.currentTarget;
    const formData = new FormData(form);
    const currentPassword = formData.get('current_password') as string;
    const newPassword = formData.get('new_password') as string;
    const confirmPassword = formData.get('confirm_password') as string;

    // Validation
    if (!currentPassword || !newPassword || !confirmPassword) {
      toast({ title: 'All fields are required', variant: 'destructive' });
      return false;
    }

    if (newPassword !== confirmPassword) {
      toast({ title: 'New passwords do not match', variant: 'destructive' });
      return false;
    }

    if (newPassword.length < 8) {
      toast({ title: 'New password must be at least 8 characters', variant: 'destructive' });
      return false;
    }

    try {
      setIsSubmitting(true);
      await changePassword(currentPassword, newPassword);

      toast({ title: 'Password updated successfully', variant: 'success' });
      form.reset();
    } catch (err) {
      console.error('Failed to update password:', err);
      toast({ title: 'Failed to update password', description: err instanceof Error ? err.message : undefined, variant: 'destructive' });
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
              Password
            </h3>
            <p className="mt-1 text-muted">
              Update your password.
            </p>
          </div>
          <div className="mt-5 md:mt-0 md:col-span-2">
            <form onSubmit={handlePasswordSubmit} className="space-y-6">
              <div>
                <label htmlFor="current_password" className="form-label">
                  Current Password
                </label>
                <input
                  type="password"
                  name="current_password"
                  id="current_password"
                  className="form-input"
                />
              </div>
              <div>
                <label htmlFor="new_password" className="form-label">
                  New Password
                </label>
                <input
                  type="password"
                  name="new_password"
                  id="new_password"
                  className="form-input"
                />
              </div>
              <div>
                <label htmlFor="confirm_password" className="form-label">
                  Confirm New Password
                </label>
                <input
                  type="password"
                  name="confirm_password"
                  id="confirm_password"
                  className="form-input"
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="btn-primary ml-3"
                >
                  {isSubmitting ? 'Updating...' : 'Update Password'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
