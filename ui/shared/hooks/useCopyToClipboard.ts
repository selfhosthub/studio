// ui/shared/hooks/useCopyToClipboard.ts

import { useCallback, useState } from 'react';
import { useToast } from '@/features/toast';
import { TIMEOUTS } from '@/shared/lib/constants';

/** Copies text, flags copied for the feedback window, and toasts when the browser refuses. */
export function useCopyToClipboard() {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);

  const copy = useCallback(
    async (text: string): Promise<boolean> => {
      try {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), TIMEOUTS.COPY_FEEDBACK);
        return true;
      } catch {
        setCopied(false);
        toast({
          title: 'Copy failed',
          description: 'The browser blocked clipboard access. Select the text and copy it instead.',
          variant: 'destructive',
        });
        return false;
      }
    },
    [toast],
  );

  return { copied, copy };
}
