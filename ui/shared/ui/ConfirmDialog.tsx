// ui/shared/ui/ConfirmDialog.tsx

'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Description, Dialog, DialogBackdrop, DialogPanel, DialogTitle } from '@headlessui/react';
import { AlertTriangle } from 'lucide-react';
import { DIALOG_PANEL_HEIGHT_CLASS, DIALOG_SCROLL_CLASS, DIALOG_WRAPPER_CLASS } from './dialogLayout';

export type ConfirmVariant = 'default' | 'danger' | 'warning';

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: ConfirmVariant;
}

export interface PromptTextOptions extends ConfirmOptions {
  inputLabel: string;
  inputPlaceholder?: string;
}

export type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

export type PromptTextFn = (options: PromptTextOptions) => Promise<string | null>;

export interface ConfirmDialogProps extends ConfirmOptions {
  isOpen: boolean;
  inputLabel?: string;
  inputPlaceholder?: string;
  inputValue?: string;
  onInputChange?: (value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  isOpen,
  message,
  title,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  inputLabel,
  inputPlaceholder,
  inputValue = '',
  onInputChange,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const danger = variant === 'danger';
  const warning = variant === 'warning';
  const confirmClass = danger ? 'btn-danger' : warning ? 'btn-warning' : 'btn-primary';
  const cautious = danger || warning;

  // Enter confirms a plain dialog from anywhere except the Cancel button; a cautious one only from its confirm button
  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' || cautious || inputLabel) return;
    if ((event.target as HTMLElement).dataset?.confirmRole === 'cancel') return;
    event.preventDefault();
    onConfirm();
  };

  return (
    <Dialog open={isOpen} onClose={onCancel} role="alertdialog" className="relative z-50">
      <DialogBackdrop
        transition
        className="fixed inset-0 bg-black/50 transition-opacity duration-200 ease-out data-[closed]:opacity-0"
      />
      <div className={DIALOG_WRAPPER_CLASS}>
        <DialogPanel
          transition
          onKeyDown={handleKeyDown}
          data-testid="confirm-dialog"
          className={`flex ${DIALOG_PANEL_HEIGHT_CLASS} max-w-md w-full flex-col bg-card rounded-lg shadow-xl transition duration-200 ease-out data-[closed]:opacity-0 data-[closed]:scale-95`}
        >
          <div data-testid="confirm-dialog-body" className={`p-6 flex gap-4 min-h-0 ${DIALOG_SCROLL_CLASS}`}>
            {cautious && (
              <div className="flex-shrink-0">
                <AlertTriangle className={`w-6 h-6 ${danger ? 'text-error' : 'text-warning'}`} aria-hidden="true" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <DialogTitle className="text-lg font-semibold text-primary">{title}</DialogTitle>
              <Description className="mt-2 text-sm text-secondary whitespace-pre-line break-words">
                {message}
              </Description>
              {inputLabel && (
                <div className="mt-4">
                  <label htmlFor="confirm-dialog-input" className="form-label">
                    {inputLabel}
                  </label>
                  <textarea
                    id="confirm-dialog-input"
                    data-testid="confirm-dialog-input"
                    className="form-input"
                    rows={3}
                    value={inputValue}
                    placeholder={inputPlaceholder}
                    onChange={(e) => onInputChange?.(e.target.value)}
                  />
                </div>
              )}
            </div>
          </div>
          <div className="shrink-0 px-6 pb-6 flex justify-end gap-3">
            <button
              type="button"
              autoFocus={cautious}
              className="btn-cancel"
              data-confirm-role="cancel"
              data-testid="confirm-dialog-cancel"
              onClick={onCancel}
            >
              {cancelLabel}
            </button>
            <button
              type="button"
              autoFocus={!cautious}
              className={confirmClass}
              data-confirm-role="confirm"
              data-testid="confirm-dialog-confirm"
              onClick={onConfirm}
            >
              {confirmLabel}
            </button>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  );
}

const ConfirmContext = createContext<ConfirmFn | undefined>(undefined);
const PromptTextContext = createContext<PromptTextFn | undefined>(undefined);

// Resolves false outside a provider so a missing provider never runs the guarded action
const declineWithoutProvider: ConfirmFn = () => Promise.resolve(false);
const cancelPromptWithoutProvider: PromptTextFn = () => Promise.resolve(null);

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions & Partial<PromptTextOptions>>({ title: '', message: '' });
  const [isOpen, setIsOpen] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const inputValueRef = useRef('');
  const resolverRef = useRef<((value: string | null) => void) | null>(null);

  const settle = useCallback((confirmed: boolean) => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    setIsOpen(false);
    resolve?.(confirmed ? inputValueRef.current : null);
  }, []);

  const open = useCallback((input: ConfirmOptions & Partial<PromptTextOptions>) => {
    // A new request cancels any request still open
    resolverRef.current?.(null);
    inputValueRef.current = '';
    setInputValue('');
    setOptions(input);
    setIsOpen(true);
    return new Promise<string | null>((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  const confirm = useCallback<ConfirmFn>(
    async (input) => (await open({ ...input, inputLabel: undefined })) !== null,
    [open],
  );

  const promptText = useCallback<PromptTextFn>(async (input) => {
    const value = await open(input);
    return value === null ? null : value.trim();
  }, [open]);

  // Unmounting with a request open resolves it as cancelled
  useEffect(() => () => resolverRef.current?.(null), []);

  return (
    <ConfirmContext.Provider value={confirm}>
      <PromptTextContext.Provider value={promptText}>
        {children}
        <ConfirmDialog
          {...options}
          isOpen={isOpen}
          inputValue={inputValue}
          onInputChange={(value) => {
            inputValueRef.current = value;
            setInputValue(value);
          }}
          onConfirm={() => settle(true)}
          onCancel={() => settle(false)}
        />
      </PromptTextContext.Provider>
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  return useContext(ConfirmContext) ?? declineWithoutProvider;
}

// Confirm dialog with a free-text field; resolves the trimmed text, or null when cancelled
export function usePromptText(): PromptTextFn {
  return useContext(PromptTextContext) ?? cancelPromptWithoutProvider;
}
