// ui/app/register/page.tsx

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useUser } from '@/entities/user';
import { useRegistrationSettings } from '@/entities/registration';

function RegisterContent() {
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    password: '',
    confirmPassword: '',
    agreeToTerms: false,
  });
  const { register, isLoading, error, status, user } = useUser();
  const { allowRegistration, isLoading: regLoading } = useRegistrationSettings();
  const [formErrors, setFormErrors] = useState<{[key: string]: string}>({});
  const router = useRouter();

  // Note: Don't redirect authenticated users here - the UserContext's register()
  // function handles the redirect to branding page after successful registration.
  // We also don't want to interfere if a logged-in user wants to view the register page.

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));

    // Clear error when user starts typing or checks
    if (formErrors[name]) {
      setFormErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const validateForm = () => {
    const newErrors: {[key: string]: string} = {};

    if (!formData.firstName.trim()) {
      newErrors.firstName = 'First name is required';
    }

    if (!formData.lastName.trim()) {
      newErrors.lastName = 'Last name is required';
    }

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Email is invalid';
    }

    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }

    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    if (!formData.agreeToTerms) {
      newErrors.agreeToTerms = 'You must agree to the Terms of Service and Privacy Policy';
    }

    setFormErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    await register(formData.firstName, formData.lastName, formData.email, formData.password);
  };

  const handleLogout = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('workflowUser');
      localStorage.removeItem('token');
      window.location.reload();
    }
  };

  // Guard: show unavailable message when registration is disabled
  if (!regLoading && !allowRegistration) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-card">
        <div className="text-center px-4">
          <h1 className="text-3xl font-bold text-primary mb-4">Registration Unavailable</h1>
          <p className="text-secondary mb-6">
            New account registration is currently disabled.
          </p>
          <Link href="/login" className="text-info font-semibold hover:underline">
            Sign in to an existing account
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex bg-card">
      <div className="flex flex-col md:flex-row w-full">
        {/* Left Section: Hero/Info */}
        <div className="hidden md:block w-1/2 bg-gradient-to-br from-indigo-700 to-purple-800 p-12 text-white"> {/* css-check-ignore: no semantic token */}
              <div className="h-full flex flex-col justify-center">
                <h3 className="text-3xl font-bold mb-6">Join Our Platform</h3>
                <p className="text-lg mb-8">
                  Create an account to start managing your team&apos;s workflows, track progress in real-time, and improve collaboration across your organization.
                </p>
                <ul className="space-y-4">
                  <li className="flex items-center">
                    <svg className="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>Create custom workflow templates</span>
                  </li>
                  <li className="flex items-center">
                    <svg className="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>Invite your team members</span>
                  </li>
                  <li className="flex items-center">
                    <svg className="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>Track projects from start to finish</span>
                  </li>
                </ul>
          </div>
        </div>

        {/* Right Section: Registration Form */}
        <div className="w-full md:w-1/2 p-8 md:p-12">
          <div className="max-w-md mx-auto">
            <h2 className="text-3xl font-bold text-primary mb-8">Create an Account</h2>

            {/* Show message if user is already logged in */}
            {status === 'authenticated' && user && (
              <div className="mb-6 bg-info-subtle border border-info text-info px-4 py-3 rounded-lg">
                <p className="mb-2">You are already logged in as <strong>{user.username}</strong>.</p>
                <div className="flex space-x-3">
                  <button
                    onClick={() => router.push('/dashboard')}
                    className="text-sm btn-primary px-3 py-1"
                  >
                    Go to Dashboard
                  </button>
                  <button
                    onClick={handleLogout}
                    className="btn-secondary text-sm"
                  >
                    Register New Account
                  </button>
                </div>
              </div>
            )}

            {error && (
              <div className="mb-6 bg-danger-subtle border border-danger text-danger px-4 py-3 rounded-lg">
                {error}
              </div>
            )}

            {/* Only show the form if user is not authenticated */}
            {status !== 'authenticated' && (
              <form onSubmit={handleSubmit}>
                <div className="mb-6">
                  <label htmlFor="firstName" className="block text-sm font-medium text-secondary mb-2">
                    First Name
                  </label>
                  <input
                    id="firstName"
                    name="firstName"
                    type="text"
                    value={formData.firstName}
                    onChange={handleChange}
                    className={`w-full p-3 border ${formErrors.firstName ? 'border-danger' : 'border-primary'} rounded-lg bg-card text-primary focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-info`}
                    placeholder="John"
                  />
                  {formErrors.firstName && <p className="mt-1 text-sm text-danger">{formErrors.firstName}</p>}
                </div>

                <div className="mb-6">
                  <label htmlFor="lastName" className="block text-sm font-medium text-secondary mb-2">
                    Last Name
                  </label>
                  <input
                    id="lastName"
                    name="lastName"
                    type="text"
                    value={formData.lastName}
                    onChange={handleChange}
                    className={`w-full p-3 border ${formErrors.lastName ? 'border-danger' : 'border-primary'} rounded-lg bg-card text-primary focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-info`}
                    placeholder="Doe"
                  />
                  {formErrors.lastName && <p className="mt-1 text-sm text-danger">{formErrors.lastName}</p>}
                </div>

                <div className="mb-6">
                  <label htmlFor="email" className="block text-sm font-medium text-secondary mb-2">
                    Email Address
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="text"
                    value={formData.email}
                    onChange={handleChange}
                    className={`w-full p-3 border ${formErrors.email ? 'border-danger' : 'border-primary'} rounded-lg bg-card text-primary focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-info`}
                    placeholder="you@example.com"
                  />
                  {formErrors.email && <p className="mt-1 text-sm text-danger">{formErrors.email}</p>}
                </div>

                <div className="mb-6">
                  <label htmlFor="password" className="block text-sm font-medium text-secondary mb-2">
                    Password
                  </label>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    value={formData.password}
                    onChange={handleChange}
                    className={`w-full p-3 border ${formErrors.password ? 'border-danger' : 'border-primary'} rounded-lg bg-card text-primary focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-info`}
                    placeholder="••••••••"
                  />
                  {formErrors.password && <p className="mt-1 text-sm text-danger">{formErrors.password}</p>}
                </div>

                <div className="mb-6">
                  <label htmlFor="confirmPassword" className="block text-sm font-medium text-secondary mb-2">
                    Confirm Password
                  </label>
                  <input
                    id="confirmPassword"
                    name="confirmPassword"
                    type="password"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    className={`w-full p-3 border ${formErrors.confirmPassword ? 'border-danger' : 'border-primary'} rounded-lg bg-card text-primary focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-info`}
                    placeholder="••••••••"
                  />
                  {formErrors.confirmPassword && <p className="mt-1 text-sm text-danger">{formErrors.confirmPassword}</p>}
                </div>

                <div className="mb-6">
                  <label className={`flex items-start cursor-pointer${formErrors.agreeToTerms ? 'text-danger' : ''}`}>
                    <input
                      type="checkbox"
                      name="agreeToTerms"
                      checked={formData.agreeToTerms}
                      onChange={handleChange}
                      className={`mt-1 mr-3 h-4 w-4 rounded border-primary text-info focus:ring-blue-500${formErrors.agreeToTerms ? 'border-danger' : ''}`}
                    />
                    <span className="text-sm text-secondary">
                      I agree to the{' '}
                      <Link href="/terms" className="text-info hover:underline" target="_blank">
                        Terms of Service
                      </Link>
                      {' '}and{' '}
                      <Link href="/privacy" className="text-info hover:underline" target="_blank">
                        Privacy Policy
                      </Link>
                    </span>
                  </label>
                  {formErrors.agreeToTerms && <p className="mt-1 text-sm text-danger">{formErrors.agreeToTerms}</p>}
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className={`w-full btn-primary py-3 rounded-lg font-semibold transition duration-300 ${
                    isLoading ? 'opacity-70 cursor-not-allowed' : ''
                  }`}
                >
                  {isLoading ? 'Creating account...' : 'Create Account'}
                </button>
              </form>
            )}

            <div className="mt-8 text-center">
              <p className="text-secondary">
                Already have an account?{' '}
                <Link href="/login" className="text-info font-semibold hover:underline">
                  Sign in
                </Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Register() {
  return <RegisterContent />;
}