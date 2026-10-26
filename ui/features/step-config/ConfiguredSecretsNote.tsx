// ui/features/step-config/ConfiguredSecretsNote.tsx

import React from 'react';

export type SecretPathSegment = string | number;
export type SecretPath = SecretPathSegment[];

// Item keys that name the entry of a name/value pair
const PAIR_NAME_FIELDS = ['key', 'name', 'header'];

// Readable label for a stored-secret path under value: the pair's name, or a dotted path
export function configuredSecretLabel(value: unknown, path: SecretPath): string {
  const last = path.length - 1;
  if (last >= 1 && path[last] === 'value' && typeof path[last - 1] === 'number') {
    let node: unknown = value;
    for (const seg of path.slice(0, last)) node = node != null && typeof node === 'object' ? (node as any)[seg] : undefined;
    const item = node as Record<string, unknown> | undefined;
    const name = item && PAIR_NAME_FIELDS.map((f) => item[f]).find((n) => typeof n === 'string' && n);
    if (name) return name as string;
  }
  return path.reduce<string>((out, seg) => (typeof seg === 'number' ? `${out}[${seg}]` : out ? `${out}.${seg}` : seg), '');
}

// Paths under key of the sealed parameter paths, each relative to key
export function secretPathsUnder(paths: SecretPath[], key: SecretPathSegment): SecretPath[] {
  return paths.filter((p) => p.length > 1 && p[0] === key).map((p) => p.slice(1));
}

interface ConfiguredSecretsNoteProps {
  value: unknown;
  paths: SecretPath[];
  testId?: string;
}

// Note listing stored secrets inside a value the viewer cannot read, which are kept on save
export function ConfiguredSecretsNote({ value, paths, testId = 'configured-secrets-note' }: ConfiguredSecretsNoteProps) {
  if (paths.length === 0) return null;
  const labels = paths.map((p) => configuredSecretLabel(value, p));
  return (
    <p className="mb-1 text-xs text-secondary" data-testid={testId}>
      Configured and kept: <span className="font-mono">{labels.join(', ')}</span>. Ask an admin to change {labels.length === 1 ? 'it' : 'them'}.
    </p>
  );
}

export default ConfiguredSecretsNote;
