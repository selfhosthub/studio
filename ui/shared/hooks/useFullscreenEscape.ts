// ui/shared/hooks/useFullscreenEscape.ts

import { useEffect } from 'react';

/** Calls onExit on Escape while active, unless a dialog is open to take the key first. */
export function useFullscreenEscape(active: boolean, onExit: () => void): void {
  useEffect(() => {
    if (!active) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return;
      onExit();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [active, onExit]);
}
