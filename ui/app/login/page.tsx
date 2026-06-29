// ui/app/login/page.tsx

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useUser } from '@/entities/user';
import { useRegistrationSettings } from '@/entities/registration';
import { Navbar } from '@/widgets/layout';

export default function Login() {
  const [usernameOrEmail, setUsernameOrEmail] = useState('');
  const [password, setPassword] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const { login, isLoading, error, status } = useUser();
  const { allowRegistration } = useRegistrationSettings();
  const router = useRouter();

  // Redirect already-authenticated users to dashboard
  useEffect(() => {
    if (status === 'authenticated') {
      router.push('/dashboard');
    }
  }, [status, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);

    if (!usernameOrEmail.trim()) {
      setValidationError('Username or email is required');
      return;
    }

    if (!password) {
      setValidationError('Password is required');
      return;
    }

    // If input contains @, validate as email format
    if (usernameOrEmail.includes('@')) {
      const isValidEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(usernameOrEmail);
      if (!isValidEmail) {
        setValidationError('Please enter a valid email address');
        return;
      }
    }

    await login(usernameOrEmail, password);
  };

  return (
    <>
      <Navbar />
    <div className="min-h-screen flex bg-card">
      {/* Left Section: Login Form */}
      <div className="w-full md:w-1/2 p-8 md:p-12">
        <div className="max-w-md mx-auto">
          <h1 className="text-3xl font-bold text-primary mb-8">Welcome Back</h1>

          {(error || validationError) && (
            <div className="mb-6 alert alert-error alert-error-text">
              {error || validationError}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="mb-6">
              <label htmlFor="usernameOrEmail" className="form-label">
                Username or Email
              </label>
              <input
                id="usernameOrEmail"
                type="text"
                value={usernameOrEmail}
                onChange={(e) => setUsernameOrEmail(e.target.value)}
                className="form-input"
                placeholder="Enter your username or email"
              />
            </div>

            <div className="mb-6">
              <label htmlFor="password" className="form-label">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="form-input"
              />
            </div>

            <button
              type="submit"
              className="w-full btn-primary"
              disabled={isLoading}
            >
              {isLoading ? 'Logging in...' : 'Sign in'}
            </button>
          </form>

          {allowRegistration && (
            <div className="mt-8 text-center">
              <p className="text-secondary">
                Don&apos;t have an account yet?{' '}
                <Link href="/register" className="link font-semibold">
                  Sign up
                </Link>
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Right Section: Hero/Info */}
      <div className="hidden md:block w-1/2 bg-gradient-to-br from-blue-600 to-indigo-800 p-12 text-white">
        <div className="h-full flex flex-col justify-center">
          <h2 className="text-3xl font-bold mb-6">Streamline Your Workflow</h2>
          <p className="text-lg mb-8">
            Log in to access your personalized dashboard and continue managing your team&apos;s workflow processes.
          </p>
          <ul className="space-y-4">
            <li className="flex items-center">
              <svg className="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span>Track projects end-to-end</span>
            </li>
            <li className="flex items-center">
              <svg className="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span>Real-time collaboration</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
    </>
  );
}