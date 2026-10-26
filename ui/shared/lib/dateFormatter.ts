// ui/shared/lib/dateFormatter.ts

/** Formats a date as "YYYY-MM-DD HH:mm" (or "YYYY-MM-DD" with time: false) in the viewer's local time zone. */
export function formatDate(dateString: string | Date, { time = true }: { time?: boolean } = {}): string {
  const date = typeof dateString === 'string' ? new Date(dateString) : dateString;

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  if (!time) return `${year}-${month}-${day}`;
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');

  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

/** Formats an age in seconds as "Ns ago", or "just now" when the age is negative (clock skew). */
export function formatSecondsAgo(seconds: number): string {
  return seconds < 0 ? 'just now' : `${seconds}s ago`;
}

export function formatRelativeTime(dateString: string | Date): string {
  const date = typeof dateString === 'string' ? new Date(dateString) : dateString;
  const now = new Date();

  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) {
    return 'just now';
  } else if (diffMins < 60) {
    return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
  } else if (diffDays < 7) {
    return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
  } else {
    return formatDate(date);
  }
}