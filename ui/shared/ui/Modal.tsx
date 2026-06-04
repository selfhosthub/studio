// ui/shared/ui/Modal.tsx

'use client';

import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from '@headlessui/react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  /** When true, renders a full-screen panel with no padding/centering wrapper. Used for lightbox-style viewers. */
  fullScreen?: boolean;
  /** Override the default panel classes (bg, rounded, shadow, etc.). */
  panelClassName?: string;
  /** Override the default backdrop classes. */
  backdropClassName?: string;
  children: React.ReactNode;
}

const sizeClasses = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
  full: 'max-w-6xl',
};

export function Modal({
  isOpen,
  onClose,
  title,
  size = 'md',
  fullScreen = false,
  panelClassName,
  backdropClassName,
  children,
}: ModalProps) {
  if (fullScreen) {
    return (
      <Dialog open={isOpen} onClose={onClose} className="relative z-50">
        <DialogPanel
          transition
          className={panelClassName ?? 'fixed inset-0 bg-black/90 flex flex-col transition duration-200 ease-out data-[closed]:opacity-0'}
        >
          {children}
        </DialogPanel>
      </Dialog>
    );
  }

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      {/* Backdrop */}
      <DialogBackdrop
        transition
        className={backdropClassName ?? 'fixed inset-0 bg-black/50 transition-opacity duration-200 ease-out data-[closed]:opacity-0'}
      />

      {/* Panel wrapper */}
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel
          transition
          className={panelClassName ?? `${sizeClasses[size]} w-full bg-card rounded-lg shadow-xl transition duration-200 ease-out data-[closed]:opacity-0 data-[closed]:scale-95`}
        >
          {title && (
            <DialogTitle className="text-lg font-semibold p-4 border-b">
              {title}
            </DialogTitle>
          )}
          {children}
        </DialogPanel>
      </div>
    </Dialog>
  );
}
