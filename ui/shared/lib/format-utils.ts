// ui/shared/lib/format-utils.ts

export function formatFileSize(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

/** Examples: "0:05", "1:23", "1:02:05". */
export function formatDuration(seconds: number): string {
  const totalSeconds = Math.round(seconds);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Picks the singular or plural noun for a count: plural(1, 'connection') is "connection". */
export function plural(count: number, noun: string): string {
  return count === 1 ? noun : `${noun}s`;
}

/** Turns a status code into words: formatStatus('waiting_for_approval') is "waiting for approval". */
export function formatStatus(status: string): string {
  if (status === 'processing') return 'running';
  return status.replace(/_/g, ' ');
}
