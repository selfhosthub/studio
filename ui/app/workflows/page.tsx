// ui/app/workflows/page.tsx

import { redirect } from 'next/navigation';

// Redirect from /workflows to /workflows/list
export default function WorkflowsPage() {
  redirect('/workflows/list');
}