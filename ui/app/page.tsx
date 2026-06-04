// ui/app/page.tsx

export const dynamic = 'force-dynamic';

import { PublicNavbar, PublicFooter } from '@/widgets/layout';
import HomeContent from '@/widgets/layout/HomeContent';

export default function Home() {
  return (
    <main className="flex flex-col bg-card">
      <PublicNavbar />
      <div className="min-h-[calc(100dvh-3rem)]">
        <HomeContent />
      </div>
      <PublicFooter />
    </main>
  );
}
