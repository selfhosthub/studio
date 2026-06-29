// ui/shared/types/prompt.ts

export interface PromptChunk {
  text: string;
  variable?: string | null;
  order: number;
  role?: string | null; // "system" | "user" | "assistant"; null defaults to "user"
}

export interface PromptVariable {
  name: string;
  label: string;
  type: string; // "string" | "enum" | "number"
  options?: string[] | null;
  default?: string | null;
  required?: boolean;
}

export interface Prompt {
  id: string;
  organization_id: string;
  name: string;
  description?: string | null;
  category: string;
  chunks: PromptChunk[];
  variables: PromptVariable[];
  is_enabled: boolean;
  source: string; // "marketplace" | "custom" | "super_admin" | "uninstalled"
  marketplace_slug?: string | null;
  created_by?: string | null;
  scope: string; // "personal" | "organization"
  visibility?: string; // "private" | "staging" | "public"
  publish_status?: string | null; // "pending" | "rejected" | null
  created_at?: string;
  updated_at?: string;
}

export interface PromptCreate {
  name: string;
  description?: string | null;
  category: string;
  chunks: PromptChunk[];
  variables: PromptVariable[];
  scope?: string; // "personal" | "organization"; omit to let the API apply the per-role default
}

export interface PromptUpdate {
  name?: string;
  description?: string;
  category?: string;
  chunks?: PromptChunk[];
  variables?: PromptVariable[];
  is_enabled?: boolean;
}

export interface AssembleMessage {
  role: string;
  content: string;
}

export interface AssembleResponse {
  messages: AssembleMessage[];
}
