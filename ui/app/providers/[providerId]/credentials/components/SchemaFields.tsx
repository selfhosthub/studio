// ui/app/providers/[providerId]/credentials/components/SchemaFields.tsx

import { ExternalLink } from 'lucide-react';
import type { CredentialSchema } from '../types';

interface SchemaFieldsProps {
  credentialSchema: CredentialSchema;
  schemaValues: Record<string, string>;
  setSchemaValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  idPrefix?: string;
}

/**
 * Schema-driven credential fields rendered from the provider's credential_schema.
 * Used in both add and edit modals.
 */
export function SchemaFields({
  credentialSchema,
  schemaValues,
  setSchemaValues,
  idPrefix = 'schema',
}: SchemaFieldsProps) {
  return (
    <div className="space-y-4">
      {/* Instructions banner if present */}
      {credentialSchema['x-ui-hints']?.instructions && (
        <div className="alert alert-info">
          <p className="text-sm">
            {credentialSchema['x-ui-hints'].instructions}
          </p>
        </div>
      )}

      {Object.entries(credentialSchema.properties || {}).map(([fieldKey, fieldSchema]) => {
        const isRequired = (credentialSchema.required || []).includes(fieldKey);
        const isPassword = fieldSchema.format === 'password';
        const hints = fieldSchema['x-ui-hints'] || {};
        const dependsOn = hints.depends_on;
        const isDependencyMet = !dependsOn || !!schemaValues[dependsOn]?.trim();

        // Build generate URL if template exists
        let generateUrl = '';
        if (hints.generate_url_template && isDependencyMet) {
          generateUrl = hints.generate_url_template.replace(
            /\{(\w+)\}/g,
            (_: string, key: string) => encodeURIComponent(schemaValues[key] || '')
          );
        }

        return (
          <div key={fieldKey} className="space-y-2">
            {/* Step title if present */}
            {hints.step_title && (
              <div className="flex items-center gap-2">
                {hints.step && (
                  <span className="flex items-center justify-center w-6 h-6 rounded-full bg-info-subtle text-info text-xs font-medium">
                    {hints.step}
                  </span>
                )}
                <span className="text-sm font-medium text-secondary">
                  {hints.step_title}
                </span>
              </div>
            )}

            <div>
              <label htmlFor={`${idPrefix}_${fieldKey}`} className="form-label">
                {fieldSchema.title || fieldKey} {isRequired && '*'}
              </label>
              <input
                type={isPassword ? 'password' : 'text'}
                id={`${idPrefix}_${fieldKey}`}
                required={isRequired}
                value={schemaValues[fieldKey] || ''}
                onChange={(e) => setSchemaValues({ ...schemaValues, [fieldKey]: e.target.value })}
                className="form-input-mono"
                placeholder={fieldSchema.examples?.[0] || ''}
                autoComplete="off"
              />

              {/* Help URL link */}
              {hints.help_url && (
                <a
                  href={hints.help_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-xs text-info hover:text-info"
                >
                  <ExternalLink className="w-3 h-3" />
                  {hints.help_link_text || 'Learn more'}
                </a>
              )}

              {/* Generate URL button */}
              {hints.generate_url_template && (
                <div className="mt-2">
                  <a
                    href={isDependencyMet ? generateUrl : undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                      isDependencyMet
                        ? 'bg-info-subtle text-info hover:bg-blue-200 dark:hover:bg-blue-800 cursor-pointer' // css-check-ignore: no semantic token for hover state
                        : 'bg-card text-muted dark:text-secondary cursor-not-allowed'
                    }`}
                    onClick={(e) => !isDependencyMet && e.preventDefault()}
                  >
                    <ExternalLink className="w-3 h-3" />
                    {hints.generate_button_text || 'Generate'}
                  </a>
                  {!isDependencyMet && dependsOn && (
                    <span className="ml-2 text-xs text-muted dark:text-secondary">
                      Enter {credentialSchema.properties[dependsOn]?.title || dependsOn} first
                    </span>
                  )}
                </div>
              )}

              {/* Description */}
              {fieldSchema.description && (
                <p className="form-helper">
                  {fieldSchema.description}
                </p>
              )}

              {/* Additional help text */}
              {hints.help_text && (
                <p className="form-helper italic">
                  {hints.help_text}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
