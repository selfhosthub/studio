// ui/features/toast/provider.tsx

'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react';
import { TIMEOUTS } from '@/shared/lib/constants';

export interface ToastProps {
  id?: string;
  title?: string;
  description?: string;
  variant?: 'default' | 'success' | 'destructive' | 'info';
  duration?: number;
  persistent?: boolean;
}

interface ToastContextType {
  toast: (props: ToastProps) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

interface ToastItem extends ToastProps {
  id: string;
  isVisible: boolean;
}

function ToastNotification({
  toast,
  onClose,
}: {
  toast: ToastItem;
  onClose: (id: string) => void;
}) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Trigger animation on mount
    const showTimer = setTimeout(() => setIsVisible(true), 10);

    if (toast.persistent) {
      return () => clearTimeout(showTimer);
    }

    // Auto-hide after duration
    const hideTimer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(() => onClose(toast.id), TIMEOUTS.ANIMATION_FADE);
    }, toast.duration || TIMEOUTS.TOAST_DEFAULT);

    return () => {
      clearTimeout(showTimer);
      clearTimeout(hideTimer);
    };
  }, [toast.id, toast.duration, toast.persistent, onClose]);

  const handleClose = () => {
    setIsVisible(false);
    setTimeout(() => onClose(toast.id), TIMEOUTS.ANIMATION_FADE);
  };

  const variantStyles = {
    default: 'bg-card border-primary',
    success: 'toast-bg-success border-success',
    destructive: 'toast-bg-destructive border-danger',
    info: 'toast-bg-info border-info',
  };

  const iconStyles = {
    default: 'text-secondary',
    success: 'text-white',
    destructive: 'text-white',
    info: 'text-white',
  };

  const textStyles = {
    default: { title: 'text-primary', description: 'text-secondary', close: 'text-muted hover:text-secondary' },
    success: { title: 'text-white', description: 'text-white/80', close: 'text-white/60 hover:text-white' },
    destructive: { title: 'text-white', description: 'text-white/80', close: 'text-white/60 hover:text-white' },
    info: { title: 'text-white', description: 'text-white/80', close: 'text-white/60 hover:text-white' },
  };

  const Icon = {
    default: Info,
    success: CheckCircle,
    destructive: AlertCircle,
    info: Info,
  }[toast.variant || 'default'];

  return (
    <div
      className={`max-w-md w-full transition-all duration-300 ${
        isVisible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'
      }`}
    >
      <div className={`rounded-lg shadow-lg border p-4 backdrop-blur-sm ${variantStyles[toast.variant || 'default']}`}>
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0">
            <Icon className={`w-5 h-5 ${iconStyles[toast.variant || 'default']}`} />
          </div>
          <div className="flex-1 min-w-0">
            {toast.title && (
              <p className={`text-sm font-semibold ${textStyles[toast.variant || 'default'].title}`}>
                {toast.title}
              </p>
            )}
            {toast.description && (
              <p className={`text-sm mt-1 ${textStyles[toast.variant || 'default'].description}`}>
                {toast.description}
              </p>
            )}
          </div>
          <button
            onClick={handleClose}
            className={`flex-shrink-0 transition-colors ${textStyles[toast.variant || 'default'].close}`}
            aria-label="Close notification"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsMounted(true);
  }, []);

  const addToast = useCallback((props: ToastProps) => {
    const id = props.id || `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setToasts((prev) => [...prev, { ...props, id, isVisible: true }]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      {isMounted &&
        createPortal(
          <div className="fixed top-20 right-4 z-50 flex flex-col gap-2" aria-live="polite" role="status">
            {toasts.map((t) => (
              <ToastNotification key={t.id} toast={t} onClose={removeToast} />
            ))}
          </div>,
          document.body
        )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);

  // Fallback for when used outside provider
  if (!context) {
    return {
      toast: () => {
        // Silently ignore toasts when provider is not available
      },
    };
  }

  return context;
}
