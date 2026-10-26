// ui/shared/lib/secret-labels.ts

// Secret name rule, the same pattern the API enforces on create.
export const SECRET_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
export const SECRET_NAME_RULE = 'Use letters, digits and underscores only, starting with a letter or underscore.';

const SECRET_TYPE_LABELS: Record<string, string> = {
  api_key: 'API Key',
  bearer: 'Bearer Token',
  oauth: 'OAuth Token',
  basic_auth: 'Basic Auth',
  custom: 'Custom',
  webhook_hmac: 'Webhook HMAC',
  webhook_header: 'Webhook Header',
  webhook_jwt: 'Webhook JWT',
  workflow_trigger: 'Workflow Trigger',
};

// Display label for a secret or credential type: "webhook_hmac" -> "Webhook HMAC".
export function secretTypeLabel(type: string): string {
  return SECRET_TYPE_LABELS[type] ?? type
    .split('_')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
