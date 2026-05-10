// ui/features/step-config/sections/GeneralSection.tsx

'use client';

import React from 'react';

interface GeneralSectionProps {
  name: string;
  description: string;
  onChange: (field: string, value: any) => void;
}

export default function GeneralSection({ name, description, onChange }: GeneralSectionProps) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-1">Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => onChange('name', e.target.value)}
          className="w-full p-2 border rounded"
          placeholder="Step name"
        />
      </div>
      
      <div>
        <label className="block text-sm font-medium mb-1">Description</label>
        <textarea
          value={description}
          onChange={(e) => onChange('description', e.target.value)}
          className="w-full p-2 border rounded"
          rows={3}
          placeholder="Step description"
        />
      </div>
    </div>
  );
}