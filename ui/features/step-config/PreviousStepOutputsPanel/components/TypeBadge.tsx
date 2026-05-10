// ui/features/step-config/PreviousStepOutputsPanel/components/TypeBadge.tsx

'use client';

/**
 * Type badge component matching n8n style
 */
export function TypeBadge({ type }: { type: string }) {
  const typeConfig: Record<string, { bg: string; text: string; label: string }> = {
    string: { bg: 'bg-success-subtle', text: 'text-success', label: 'AB' },
    number: { bg: 'bg-info-subtle', text: 'text-info', label: '123' },
    integer: { bg: 'bg-info-subtle', text: 'text-info', label: '123' },
    boolean: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-400', label: 'T/F' }, // css-check-ignore: no semantic token
    array: { bg: 'bg-critical-subtle', text: 'text-critical', label: '[ ]' },
    object: { bg: 'bg-warning-subtle', text: 'text-warning', label: '{ }' },
  };

  const config = typeConfig[type] || { bg: 'bg-card', text: 'text-secondary', label: '?' };

  return (
    <span className={`inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-mono rounded ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
}
