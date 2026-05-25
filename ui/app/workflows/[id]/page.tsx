// ui/app/workflows/[id]/page.tsx

import { redirect } from 'next/navigation';

export default async function WorkflowViewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/workflows/${id}/edit`);
}
