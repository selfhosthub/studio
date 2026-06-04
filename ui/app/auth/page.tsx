// ui/app/auth/page.tsx

'use client';

import { useAuth } from '@/features/auth';
import { Loader2 } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

export default function AuthPage() {
  // Change: Removed the unused isLoading from destructuring
  const { user, loginMutation, registerMutation } = useAuth();
  const router = useRouter();
  const [isLogin, setIsLogin] = useState(true);

  // Form state
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');

  // Validation state
  const [errors, setErrors] = useState<Record<string, string>>({});

  // If already logged in, redirect to dashboard
  useEffect(() => {
    if (user) {
      router.push('/dashboard');
    }
  }, [user, router]);

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!username) newErrors.username = 'Username is required';

    if (!isLogin && !email) {
      newErrors.email = 'Email is required';
    } else /* istanbul ignore next */ if (!isLogin && !/\S+@\S+\.\S+/.test(email)) {
      /* istanbul ignore next */
      newErrors.email = 'Email is invalid';
    }

    if (!password) {
      newErrors.password = 'Password is required';
    } else if (!isLogin && password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }

    if (!isLogin && password !== passwordConfirm) {
      newErrors.passwordConfirm = 'Passwords do not match';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) return;

    if (isLogin) {
      loginMutation.mutate({ username, password });
    } else {
      registerMutation.mutate({ username, email, password });
    }
  };

  const toggleAuthMode = () => {
    setIsLogin(!isLogin);
    // Clear form fields when toggling modes
    setUsername('');
    setEmail('');
    setPassword('');
    setPasswordConfirm('');
    setErrors({});
  };

  // If user is already logged in and being redirected
  if (user) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-border" />
        <p className="ml-2">Redirecting to dashboard...</p>
      </div>
    );
  }

  // Fix status comparison - React Query uses "pending" instead of "loading"
  const isLoginLoading = loginMutation.status === 'pending';
  const isRegisterLoading = registerMutation.status === 'pending';
  const isSubmitting = isLoginLoading || isRegisterLoading;

  // Get error messages from mutations
  const loginError = loginMutation.error?.message;
  const registerError = registerMutation.error?.message;

  return (
    <div className="flex min-h-screen">
      {/* Auth Form */}
      <div className="w-full lg:w-1/2 p-8 md:p-12 flex items-center justify-center">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold">Self-Host Studio Live</h1>
            <p className="text-secondary mt-2">
              {isLogin ? 'Sign in to your account' : 'Create a new account'}
            </p>
          </div>

          {/* Show mutation errors if present */}
          {isLogin && loginError && (
            <div className="mb-6 bg-danger-subtle border border-danger text-danger px-4 py-3 rounded-lg">
              {loginError}
            </div>
          )}

          {!isLogin && registerError && (
            <div className="mb-6 bg-danger-subtle border border-danger text-danger px-4 py-3 rounded-lg">
              {registerError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="username" className="block text-sm font-medium mb-1">
                Username
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Enter your username"
              />
              {errors.username && (
                <p className="text-danger text-sm mt-1">{errors.username}</p>
              )}
            </div>

            {!isLogin && (
              <div>
                <label htmlFor="email" className="block text-sm font-medium mb-1">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Enter your email"
                />
                {errors.email && (
                  <p className="text-danger text-sm mt-1">{errors.email}</p>
                )}
              </div>
            )}

            <div>
              <label htmlFor="password" className="block text-sm font-medium mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Enter your password"
              />
              {errors.password && (
                <p className="text-danger text-sm mt-1">{errors.password}</p>
              )}
            </div>

            {!isLogin && (
              <div>
                <label htmlFor="passwordConfirm" className="block text-sm font-medium mb-1">
                  Confirm Password
                </label>
                <input
                  id="passwordConfirm"
                  type="password"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Confirm your password"
                />
                {errors.passwordConfirm && (
                  <p className="text-danger text-sm mt-1">{errors.passwordConfirm}</p>
                )}
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-primary w-full flex justify-center"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="animate-spin h-5 w-5 mr-2" />
                  <span>{isLogin ? 'Signing in...' : 'Creating account...'}</span>
                </>
              ) : (
                <span>{isLogin ? 'Sign In' : 'Create Account'}</span>
              )}
            </button>
          </form>

          <div className="mt-6 text-center">
            <button
              onClick={toggleAuthMode}
              className="text-info hover:text-info font-medium"
            >
              {isLogin ? 'Need an account? Sign up' : 'Already have an account? Sign in'}
            </button>
          </div>

          <div className="mt-8 text-center">
            <Link
              href="/"
              className="text-secondary hover:text-primary"
            >
              ← Back to home
            </Link>
          </div>
        </div>
      </div>

      {/* Hero Section */}
      <div className="hidden lg:block lg:w-1/2 bg-gray-900"> {/* css-check-ignore: dark hero background */}
        <div className="h-full flex items-center justify-center p-12 relative">
          <div className="relative z-10 text-white max-w-lg">
            <h2 className="text-4xl font-bold mb-6">Streamline Your Media Production</h2>
            <p className="text-xl mb-8">
              Studio offers comprehensive tools for studio management, media production, and team collaboration.
            </p>
            <ul className="space-y-4">
              <li className="flex items-start">
                <span className="text-success mr-2">✓</span>
                <span>Manage studio assets and bookings</span>
              </li>
              <li className="flex items-start">
                <span className="text-success mr-2">✓</span>
                <span>Coordinate team schedules and projects</span>
              </li>
              <li className="flex items-start">
                <span className="text-success mr-2">✓</span>
                <span>Track production workflows and timelines</span>
              </li>
              <li className="flex items-start">
                <span className="text-success mr-2">✓</span>
                <span>Secure self-hosted solution for your media business</span>
              </li>
            </ul>
          </div>
          <div className="absolute inset-0 bg-black opacity-40"></div>
          <div className="absolute inset-0 z-0">
            <Image
              src="/studio-pro.png"
              alt="Studio Environment"
              fill
              style={{ objectFit: 'cover' }}
              priority
            />
          </div>
        </div>
      </div>
    </div>
  );
}