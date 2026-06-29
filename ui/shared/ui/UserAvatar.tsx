// ui/shared/ui/UserAvatar.tsx

'use client';

import React from 'react';
import { resolveUploadUrl } from '@/shared/lib/config';

interface UserAvatarUser {
  first_name?: string | null;
  last_name?: string | null;
  avatar_url?: string | null;
}

interface UserAvatarProps {
  user?: UserAvatarUser | null;
  /** Tailwind sizing classes for the circle (width/height). */
  sizeClassName?: string;
  /** Tailwind text-size class for the initial fallback. */
  textClassName?: string;
  /** Optional inline style for the initial circle (e.g. branding color). */
  initialStyle?: React.CSSProperties;
  className?: string;
}

/**
 * Consistent user avatar across the app. Precedence:
 *   1. avatar_url (resolved against the API origin)
 *   2. first_name initial, else last_name initial
 *   3. gray person icon
 */
export function UserAvatar({
  user,
  sizeClassName = 'h-8 w-8',
  textClassName = 'text-sm',
  initialStyle,
  className = '',
}: UserAvatarProps) {
  const base = `${sizeClassName} rounded-full${className ? ` ${className}` : ''}`;

  if (user?.avatar_url) {
    return (
      <span className={`${base} overflow-hidden bg-card inline-block`}>
        {/* eslint-disable-next-line @next/next/no-img-element -- avatar served from API origin, not Next image domains */}
        <img
          src={resolveUploadUrl(user.avatar_url)}
          alt=""
          className="h-full w-full object-cover"
        />
      </span>
    );
  }

  const initial = user?.first_name?.[0] || user?.last_name?.[0];
  if (initial) {
    return (
      <span
        className={`${base} flex items-center justify-center font-medium uppercase ${textClassName} ${initialStyle ? '' : 'bg-input text-secondary'}`}
        style={initialStyle}
      >
        {initial}
      </span>
    );
  }

  return (
    <span className={`${base} overflow-hidden bg-input inline-block`}>
      <svg className="h-full w-full text-muted" fill="currentColor" viewBox="0 0 24 24">
        <path d="M24 20.993V24H0v-2.996A14.977 14.977 0 0112.004 15c4.904 0 9.26 2.354 11.996 5.993zM16.002 8.999a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    </span>
  );
}
