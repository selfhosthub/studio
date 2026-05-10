// ui/features/marketplace/components/CatalogStatusBanner.tsx

'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { X, WifiOff } from 'lucide-react';

const STORAGE_KEY = 'studio-catalog-warnings-dismissed';

interface CatalogStatusContextType {
  /** Called by any marketplace tab to report catalog warnings. */
  reportWarnings: (warnings: string[]) => void;
}

const CatalogStatusContext = createContext<CatalogStatusContextType>({
  reportWarnings: () => {},
});

export function useCatalogStatus() {
  return useContext(CatalogStatusContext);
}

export function CatalogStatusProvider({ children }: { children: React.ReactNode }) {
  const [warnings, setWarnings] = useState<string[]>([]);
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem(STORAGE_KEY) === 'true';
    }
    return false;
  });

  const reportWarnings = useCallback((incoming: string[]) => {
    if (incoming.length === 0) return;
    setWarnings((prev) => {
      const combined = new Set([...prev, ...incoming]);
      return Array.from(combined);
    });
  }, []);

  const handleDismiss = () => {
    setDismissed(true);
    sessionStorage.setItem(STORAGE_KEY, 'true');
  };

  return (
    <CatalogStatusContext.Provider value={{ reportWarnings }}>
      {!dismissed && warnings.length > 0 && (
        <CatalogBanner warnings={warnings} onDismiss={handleDismiss} />
      )}
      {children}
    </CatalogStatusContext.Provider>
  );
}

function CatalogBanner({ warnings, onDismiss }: { warnings: string[]; onDismiss: () => void }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), 10);
    return () => clearTimeout(timer);
  }, []);

  const handleDismiss = () => {
    setVisible(false);
    setTimeout(onDismiss, 300);
  };

  return (
    <div
      className={`transition-all duration-300 overflow-hidden ${
        visible ? 'max-h-20 opacity-100' : 'max-h-0 opacity-0'
      }`}
    >
      <div className="bg-warning-subtle border-b border-warning px-4 py-2 flex items-center gap-3">
        <WifiOff className="w-4 h-4 text-warning flex-shrink-0" />
        <p className="text-sm text-warning flex-1">
          Remote catalog unavailable. Using locally cached packages.
        </p>
        <button
          onClick={handleDismiss}
          className="p-1 hover:bg-card/20 rounded transition-colors text-warning"
          aria-label="Dismiss catalog warning"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
