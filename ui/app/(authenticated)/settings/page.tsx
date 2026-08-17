// ui/app/(authenticated)/settings/page.tsx

import { redirect } from 'next/navigation';

export default function SettingsPage() {
  // Default to the profile tab
  redirect('/settings/profile');
}
