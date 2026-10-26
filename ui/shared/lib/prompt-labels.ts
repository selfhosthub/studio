// ui/shared/lib/prompt-labels.ts

export interface CategoryOption {
  value: string;
  label: string;
}

// Category slugs offered for prompts, matching the community and Plus catalogs.
export const PROMPT_CATEGORIES = [
  'general',
  'classification',
  'copywriting',
  'extraction',
  'research',
  'rewriting',
  'scene_description',
  'story_generation',
  'summarization',
] as const;

// Title Case label for a category slug: "story_generation" -> "Story Generation".
export function formatPromptCategory(value: string): string {
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

// Shared categories plus any extra slugs not already in the list, extras sorted by label.
export function promptCategoryOptions(extra: readonly string[] = []): CategoryOption[] {
  const known = new Set<string>(PROMPT_CATEGORIES);
  const extras = Array.from(new Set(extra.filter((c) => c && !known.has(c))));
  const toOption = (value: string) => ({ value, label: formatPromptCategory(value) });
  return [
    ...PROMPT_CATEGORIES.map(toOption),
    ...extras.map(toOption).sort((a, b) => a.label.localeCompare(b.label)),
  ];
}

export type PromptSourceLabel = 'Community' | 'Plus' | 'Yours' | 'Custom';

// Who a prompt comes from: its catalog tier when installed, Yours when the current user created it, otherwise Custom.
export function promptSourceLabel(
  prompt: { source: string; tier?: string | null; created_by?: string | null },
  currentUserId?: string | null,
): PromptSourceLabel {
  if (prompt.tier === 'plus') return 'Plus';
  if (prompt.tier === 'community' || prompt.source === 'marketplace') return 'Community';
  if (currentUserId && prompt.created_by === currentUserId) return 'Yours';
  return 'Custom';
}
