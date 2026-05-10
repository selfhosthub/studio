// ui/app/files/lib/fileTypeDetector.ts

import { OrgFile } from '@/shared/types/api';

const VIDEO_EXTENSIONS = ['mp4', 'webm', 'mov', 'avi', 'mkv', 'flv', 'wmv'];
const AUDIO_EXTENSIONS = ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac', 'wma'];
const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'];

function getExtension(filename: string): string {
  const parts = filename.split('.');
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : '';
}

export function getActualFilename(resource: OrgFile): string {
  if (resource.virtual_path) {
    const parts = resource.virtual_path.split('/').filter(Boolean);
    const filename = parts[parts.length - 1];
    if (filename) return filename;
  }
  return resource.display_name;
}

export function isVideoFile(resource: OrgFile): boolean {
  return resource.mime_type.startsWith('video/') ||
    (resource.mime_type === 'application/octet-stream' && VIDEO_EXTENSIONS.includes(getExtension(getActualFilename(resource))));
}

export function isAudioFile(resource: OrgFile): boolean {
  return resource.mime_type.startsWith('audio/') ||
    (resource.mime_type === 'application/octet-stream' && AUDIO_EXTENSIONS.includes(getExtension(getActualFilename(resource))));
}

export function isImageFile(resource: OrgFile): boolean {
  return resource.mime_type.startsWith('image/') ||
    (resource.mime_type === 'application/octet-stream' && IMAGE_EXTENSIONS.includes(getExtension(getActualFilename(resource))));
}

export function getDisplayFilename(resource: OrgFile): string {
  if (resource.virtual_path) {
    const parts = resource.virtual_path.split('/');
    const filename = parts[parts.length - 1];
    if (filename && filename.includes('.')) return filename;
  }
  return resource.display_name;
}

export function getFileIcon(resource: OrgFile): string {
  if (isImageFile(resource)) return 'image';
  if (isVideoFile(resource)) return 'video';
  if (isAudioFile(resource)) return 'audio';
  if (resource.mime_type.startsWith('text/') || resource.mime_type.startsWith('application/')) return 'document';
  return 'file';
}

export function getSourceLabel(source: string): string {
  switch (source) {
    case 'job_generated': return 'Generated';
    case 'job_download': return 'Downloaded';
    case 'user_upload': return 'Uploaded';
    default: return source;
  }
}

export function getSourceColor(source: string): string {
  switch (source) {
    case 'job_generated': return 'text-success';
    case 'job_download': return 'text-info';
    case 'user_upload': return 'text-purple-600 dark:text-purple-400'; // css-check-ignore: purple brand color
    default: return 'text-secondary';
  }
}

export function formatRelativeDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
