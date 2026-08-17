// ui/app/(authenticated)/workflows/[id]/edit/components/TriggerSecretPicker.tsx

'use client';

import React, { useEffect, useState } from 'react';
import { listWorkflowTriggerSecretOptions } from '@/shared/api';
import type { TriggerSecretOption, TriggerSecretType } from '@/shared/api/workflows';

interface TriggerSecretPickerProps {
  workflowId: string;
  /** Which typed trigger secrets to offer for reuse. */
  secretType: TriggerSecretType;
  /** Mint a brand-new secret for this workflow. */
  onGenerate: () => void;
  /** Share an existing org secret (admin's choice) instead of minting. */
  onLinked: (secretId: string) => void;
  /** Label for the generate button, e.g. "Generate API key". */
  generateLabel: string;
  disabled?: boolean;
}

/**
 * The single "Generate new / Use existing…" control for any trigger credential.
 * It fetches the org's reusable secrets OF ONE TYPE (admins only; others get 403
 * → no dropdown) and offers them beside the generate button. One component for
 * every credential kind - no per-type branches at the call sites.
 */
export function TriggerSecretPicker({
  workflowId,
  secretType,
  onGenerate,
  onLinked,
  generateLabel,
  disabled = false,
}: TriggerSecretPickerProps) {
  const [options, setOptions] = useState<TriggerSecretOption[]>([]);

  useEffect(() => {
    let cancelled = false;
    listWorkflowTriggerSecretOptions(workflowId, secretType)
      .then((opts) => {
        if (!cancelled) setOptions(opts);
      })
      .catch(() => {
        // Not permitted / none - no dropdown shown.
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId, secretType]);

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onGenerate}
        disabled={disabled}
        className="btn-primary text-xs px-3 py-1.5"
      >
        {generateLabel}
      </button>
      {options.length > 0 && (
        <select
          defaultValue=""
          disabled={disabled}
          onChange={(e) => {
            if (e.target.value) onLinked(e.target.value);
          }}
          className="form-select text-xs py-1 px-1.5"
          title="Share an existing trigger secret instead of minting a new one"
        >
          <option value="">Use existing secret…</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name} (shared by {o.shared_by_count})
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
