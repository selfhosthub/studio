// ui/shared/lib/runControl.ts

interface RunControlUser {
  id?: string;
  role?: string;
}

interface RunControlInstance {
  user_id?: string | null;
}

/** True when the user may change the run: an admin or the run's owner. */
export function canControlRun(
  user: RunControlUser | null | undefined,
  instance: RunControlInstance | null | undefined,
): boolean {
  if (!user || !instance) return false;
  if (user.role === 'admin' || user.role === 'super_admin') return true;
  return !!instance.user_id && instance.user_id === user.id;
}
