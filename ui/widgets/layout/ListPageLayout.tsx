// ui/widgets/layout/ListPageLayout.tsx

import React from 'react';

interface ListPageLayoutProps {
  title: string;
  description: string;
  children: React.ReactNode;
  actionButton?: React.ReactNode;
}

export default function ListPageLayout({ title, description, children, actionButton }: ListPageLayoutProps) {
  return (
    <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
      <div className="flex flex-wrap justify-between items-center gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="text-muted">{description}</p>
        </div>
        {actionButton}
      </div>
      {children}
    </div>
  );
}