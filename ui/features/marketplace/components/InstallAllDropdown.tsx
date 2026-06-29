// ui/features/marketplace/components/InstallAllDropdown.tsx

'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Download, ChevronDown } from 'lucide-react';

interface InstallAllDropdownProps {
  hasCommunity: boolean;
  hasPlus: boolean;
  installing: 'community' | 'plus' | null;
  onInstall: (tier: 'community' | 'plus') => void;
}

export default function InstallAllDropdown({
  hasCommunity,
  hasPlus,
  installing,
  onInstall,
}: InstallAllDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (installing) {
    return (
      <button disabled className="btn-success inline-flex items-center justify-center gap-2 opacity-75">
        <Download className="w-4 h-4 animate-pulse" />
        Installing {installing}...
      </button>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="btn-success inline-flex items-center justify-center gap-2"
      >
        <Download className="w-4 h-4" />
        Install All
        <ChevronDown className="w-3 h-3" />
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-40 rounded-md shadow-lg bg-card border border-primary z-50">
          {hasCommunity && (
            <button
              onClick={() => { onInstall('community'); setOpen(false); }}
              className="w-full text-left px-4 py-2 text-sm text-secondary hover:bg-card rounded-t-md"
            >
              Community
            </button>
          )}
          {hasPlus && (
            <button
              onClick={() => { onInstall('plus'); setOpen(false); }}
              className="w-full text-left px-4 py-2 text-sm text-secondary hover:bg-card rounded-b-md"
            >
              Plus
            </button>
          )}
        </div>
      )}
    </div>
  );
}
