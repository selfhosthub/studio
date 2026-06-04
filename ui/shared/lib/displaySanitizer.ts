// ui/shared/lib/displaySanitizer.ts

const VIRTUAL_PATH_REGEX = /^\/orgs\/[a-f0-9-]+\/instances\/[a-f0-9-]+\/(.+)$/i;

const FILE_PATH_REGEX = /^\/orgs\/[a-f0-9-]+\/files\/(.+)$/i;

export interface DisplayContext {
  stepNames?: Map<string, string>;
  currentInstanceId?: string;
}

export function sanitizeVirtualPath(path: string, context?: DisplayContext): string {
  const instanceMatch = path.match(VIRTUAL_PATH_REGEX);
  if (instanceMatch) {
    const filename = instanceMatch[1];
    return `[Output: ${filename}]`;
  }

  const fileMatch = path.match(FILE_PATH_REGEX);
  if (fileMatch) {
    const filename = fileMatch[1].split('/').pop() || fileMatch[1];
    return `[File: ${filename}]`;
  }

  return path;
}

export function isVirtualPath(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  return VIRTUAL_PATH_REGEX.test(value) || FILE_PATH_REGEX.test(value);
}

export function sanitizeForDisplay(data: unknown, context?: DisplayContext): unknown {
  if (data === null || data === undefined) return data;

  if (typeof data === 'string') {
    // Avoid type guard here so TS doesn't narrow to never on the else branch.
    if (VIRTUAL_PATH_REGEX.test(data) || FILE_PATH_REGEX.test(data)) {
      return sanitizeVirtualPath(data, context);
    }
    return data.replace(
      /([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/gi,
      (match: string) => `${match.substring(0, 8)}...${match.substring(match.length - 4)}`
    );
  }

  if (Array.isArray(data)) {
    return data.map(item => sanitizeForDisplay(item, context));
  }

  if (typeof data === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(data)) {
      const lowerKey = key.toLowerCase();
      if (
        lowerKey.includes('secret') ||
        lowerKey.includes('password') ||
        lowerKey.includes('api_key') ||
        lowerKey.includes('apikey') ||
        lowerKey.includes('auth_token') ||
        lowerKey.includes('access_token') ||
        lowerKey.includes('refresh_token') ||
        lowerKey.includes('authorization') ||
        lowerKey.includes('bearer') ||
        lowerKey === 'credential_id'
      ) {
        result[key] = '[REDACTED]';
      } else {
        result[key] = sanitizeForDisplay(value, context);
      }
    }
    return result;
  }

  return data;
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}
