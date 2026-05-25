// ui/shared/types/user.ts

/** Mirrors the API JWT payload. */
export type User = {
  id: string;
  username: string;
  email: string;
  role: 'user' | 'admin' | 'super_admin';
  org_id?: string;
  org_slug?: string;
  // Not in the JWT - populated by user-profile fetches.
  first_name?: string;
  last_name?: string;
  avatar_url?: string;
};
