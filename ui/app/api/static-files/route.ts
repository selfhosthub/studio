// ui/app/api/static-files/route.ts

/**
 * Next.js API route that lists available static media files from the public folder.
 * This runs on the frontend server, so it has direct access to the public folder.
 */

import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'];
const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov'];

interface StaticFileInfo {
  path: string;
  filename: string;
  extension: string;
  media_type: 'image' | 'video';
}

export async function GET() {
  const publicDir = path.join(process.cwd(), 'public');
  const files: StaticFileInfo[] = [];

  // Scan /public/images
  const imagesDir = path.join(publicDir, 'images');
  if (fs.existsSync(imagesDir)) {
    for (const file of fs.readdirSync(imagesDir)) {
      const ext = path.extname(file).toLowerCase();
      if (IMAGE_EXTENSIONS.includes(ext)) {
        files.push({
          path: `/images/${file}`,
          filename: file,
          extension: ext,
          media_type: 'image',
        });
      }
    }
  }

  // Scan /public/videos
  const videosDir = path.join(publicDir, 'videos');
  if (fs.existsSync(videosDir)) {
    for (const file of fs.readdirSync(videosDir)) {
      const ext = path.extname(file).toLowerCase();
      if (VIDEO_EXTENSIONS.includes(ext)) {
        files.push({
          path: `/videos/${file}`,
          filename: file,
          extension: ext,
          media_type: 'video',
        });
      }
    }
  }

  // Sort by filename
  files.sort((a, b) => a.filename.localeCompare(b.filename));

  return NextResponse.json({ files });
}
