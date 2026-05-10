// ui/app/ai-agents/prompts/components/PromptForm.tsx

"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  PromptChunk,
  PromptVariable,
} from "@/shared/types/prompt";

// ============================================================================
// Types
// ============================================================================

export interface PromptFormData {
  name: string;
  description: string;
  category: string;
  chunks: PromptChunk[];
  variables: PromptVariable[];
}

interface Props {
  initialData?: PromptFormData;
  onSubmit: (data: PromptFormData) => Promise<void>;
  submitLabel: string;
}

// ============================================================================
// Constants
// ============================================================================

const CATEGORY_OPTIONS = [
  { value: "general", label: "General" },
  { value: "story_generation", label: "Story Generation" },
  { value: "scene_description", label: "Scene Description" },
  { value: "summarization", label: "Summarization" },
  { value: "classification", label: "Classification" },
  { value: "extraction", label: "Extraction" },
  { value: "rewriting", label: "Rewriting" },
];

// ============================================================================
// Helpers
// ============================================================================

/** Built-in variables injected by the server - exclude from user-defined variables. */
const BUILTIN_VARIABLES = new Set(["today_date", "today_datetime"]);

/** Extract unique {{ variable_name }} references from prompt text.
 *  Tolerates Jinja2 filters ({{ x | filter }}, {{ x|filter1|filter2 }}) and
 *  ignores {% ... %} tags and built-in variables. */
const VARIABLE_REF_RE = /\{\{\s*(\w+)(?:\s*\|[^}]*)?\s*\}\}/g;

function detectVariables(text: string): string[] {
  const regex = new RegExp(VARIABLE_REF_RE.source, "g");
  const names = new Set<string>();
  let match;
  while ((match = regex.exec(text)) !== null) {
    const name = match[1];
    if (!BUILTIN_VARIABLES.has(name)) {
      names.add(name);
    }
  }
  return Array.from(names);
}

const ROLE_PREFIX_RE = /^\[(system|user|assistant)\]\s*/i;

/** Convert flat prompt text into ordered chunks, parsing [role] prefixes.
 *  Blank lines (double newline) separate chunks; lines within a chunk are joined by \n. */
function textToChunks(text: string): PromptChunk[] {
  const blocks = text.split(/\n\n+/);
  let currentRole = "user";

  return blocks.map((block, index) => {
    const lines = block.split("\n");
    const firstLine = lines[0];
    const roleMatch = firstLine.match(ROLE_PREFIX_RE);
    let role = currentRole;

    if (roleMatch) {
      role = roleMatch[1].toLowerCase();
      lines[0] = firstLine.slice(roleMatch[0].length);
      currentRole = role;
    }

    const cleanText = lines.join("\n");
    const varMatch = cleanText.match(new RegExp(VARIABLE_REF_RE.source));
    return {
      text: cleanText,
      variable: varMatch ? varMatch[1] : null,
      order: index,
      role,
    };
  });
}

/** Convert chunks back into flat text with [role] prefixes for editing. */
function chunksToText(chunks: PromptChunk[]): string {
  const sorted = [...chunks].sort((a, b) => a.order - b.order);
  let lastRole: string | null = null;

  return sorted
    .map((c) => {
      const role = c.role || "user";
      // Only show prefix when the role changes (or for the first line)
      if (role !== lastRole) {
        lastRole = role;
        return `[${role}] ${c.text}`;
      }
      lastRole = role;
      return c.text;
    })
    .join("\n\n");
}

interface AssembledMessage {
  role: string;
  content: string;
}

/** Assemble preview as a messages array (mirrors backend logic). */
function assemblePreview(
  chunks: PromptChunk[],
  variableValues: Record<string, string>
): AssembledMessage[] {
  const sorted = [...chunks].sort((a, b) => a.order - b.order);
  const messages: AssembledMessage[] = [];

  for (const chunk of sorted) {
    if (chunk.variable) {
      const value = variableValues[chunk.variable] || "";
      if (!value) continue;
    }

    let text = chunk.text.replace(
      new RegExp(VARIABLE_REF_RE.source, "g"),
      (match, varName) => variableValues[varName] ?? match,
    );

    // textToChunks (the only producer of `chunks` here) always assigns a role,
    // so chunk.role is non-null at this point. Type is loose because PromptChunk
    // is shared with backend payloads that may carry null.
    const role = chunk.role!;
    if (messages.length > 0 && messages[messages.length - 1].role === role) {
      messages[messages.length - 1].content += "\n\n" + text;
    } else {
      messages.push({ role, content: text });
    }
  }

  return messages;
}

// ============================================================================
// Component
// ============================================================================

export default function PromptForm({
  initialData,
  onSubmit,
  submitLabel,
}: Props) {
  const [name, setName] = useState(initialData?.name || "");
  const [description, setDescription] = useState(
    initialData?.description || ""
  );
  const [category, setCategory] = useState(
    initialData?.category || "general"
  );
  const [promptText, setPromptText] = useState(
    initialData?.chunks ? chunksToText(initialData.chunks) : ""
  );
  const [variables, setVariables] = useState<PromptVariable[]>(
    initialData?.variables || []
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track raw options text per variable index so commas aren't eaten mid-edit
  const [optionsText, setOptionsText] = useState<Record<number, string>>({});

  // Preview state
  const [previewValues, setPreviewValues] = useState<Record<string, string>>(
    {}
  );
  const [showPreview, setShowPreview] = useState(false);

  // Auto-detect variables from prompt text
  const detectedVarNames = useMemo(
    () => detectVariables(promptText),
    [promptText]
  );

  // Sync detected variables with the variables list
  useEffect(() => {
    setVariables((prev) => {
      // Keep existing variables that are still detected, add new ones
      const existing = new Map(prev.map((v) => [v.name, v]));
      return detectedVarNames.map(
        (name) =>
          existing.get(name) || {
            name,
            label: name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
            type: "string",
            options: null,
            default: null,
            required: false,
          }
      );
    });
  }, [detectedVarNames]);

  // Initialize preview values from variable defaults
  useEffect(() => {
    setPreviewValues((prev) => {
      const next = { ...prev };
      for (const v of variables) {
        if (!(v.name in next)) {
          next[v.name] = v.default || "";
        }
      }
      // Remove keys not in current variables
      for (const key of Object.keys(next)) {
        if (!variables.some((v) => v.name === key)) {
          delete next[key];
        }
      }
      return next;
    });
  }, [variables]);

  const chunks = useMemo(() => textToChunks(promptText), [promptText]);
  const previewMessages = useMemo(
    () => assemblePreview(chunks, previewValues),
    [chunks, previewValues]
  );

  const updateVariable = (
    index: number,
    field: keyof PromptVariable,
    value: any
  ) => {
    setVariables((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (!promptText.trim()) {
      setError("Prompt text is required");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || "",
        category,
        chunks,
        variables,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save template");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="alert alert-error">
          <p>{error}</p>
        </div>
      )}

      {/* Name */}
      <div>
        <label htmlFor="name" className="form-label">
          Name <span className="text-danger">*</span>
        </label>
        <input
          id="name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="form-input w-full"
          placeholder="e.g. News Report Narrator"
          required
        />
      </div>

      {/* Description */}
      <div>
        <label htmlFor="description" className="form-label">
          Description
        </label>
        <input
          id="description"
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="form-input w-full"
          placeholder="Brief description of what this template does"
        />
      </div>

      {/* Category */}
      <div>
        <label htmlFor="category" className="form-label">
          Category
        </label>
        <select
          id="category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="form-select w-full"
        >
          {CATEGORY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Prompt Text */}
      <div>
        <label htmlFor="promptText" className="form-label">
          Prompt Text <span className="text-danger">*</span>
        </label>
        <p className="text-xs text-secondary mb-1">
          Prefix lines with <code className="bg-card px-1 rounded">[system]</code>,{" "}
          <code className="bg-card px-1 rounded">[user]</code>, or{" "}
          <code className="bg-card px-1 rounded">[assistant]</code> to set roles.
          Lines without a prefix inherit the previous role (default: user).
          Use <code className="bg-card px-1 rounded">{"{{ variable }}"}</code> for dynamic values,{" "}
          <code className="bg-card px-1 rounded">{"{% if %}"}</code> / <code className="bg-card px-1 rounded">{"{% else %}"}</code> for
          conditionals, and Jinja2 filters like <code className="bg-card px-1 rounded">{"{{ x|upper }}"}</code>.
          Built-in: <code className="bg-card px-1 rounded">{"{{ today_date }}"}</code>,{" "}
          <code className="bg-card px-1 rounded">{"{{ today_datetime }}"}</code>.
          Blank lines separate chunks.
        </p>
        <textarea
          id="promptText"
          value={promptText}
          onChange={(e) => setPromptText(e.target.value)}
          className="form-textarea w-full font-mono text-sm"
          rows={12}
          placeholder={`[system] You are a scriptwriter who turns articles into narrated stories.\n[user] Write a narrated story based on the article below.\nStyle: {{ style }}.\nStructure it as {{ scene_count }} scenes.`}
          required
        />
      </div>

      {/* Detected Variables */}
      {variables.length > 0 && (
        <div>
          <h3 className="form-label mb-2">
            Variables ({variables.length})
          </h3>
          <div className="space-y-3">
            {variables.map((v, i) => (
              <div
                key={v.name}
                className="border border-primary rounded-lg p-3"
              >
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  {/* Name (read-only) */}
                  <div>
                    <label htmlFor={`prompt-var-name-${v.name}`} className="text-xs text-secondary">
                      Name
                    </label>
                    <input
                      id={`prompt-var-name-${v.name}`}
                      type="text"
                      value={v.name}
                      readOnly
                      className="form-input w-full bg-surface text-sm"
                    />
                  </div>

                  {/* Label */}
                  <div>
                    <label htmlFor={`prompt-var-label-${v.name}`} className="text-xs text-secondary">
                      Label
                    </label>
                    <input
                      id={`prompt-var-label-${v.name}`}
                      type="text"
                      value={v.label}
                      onChange={(e) =>
                        updateVariable(i, "label", e.target.value)
                      }
                      className="form-input w-full text-sm"
                    />
                  </div>

                  {/* Type */}
                  <div>
                    <label htmlFor={`prompt-var-type-${v.name}`} className="text-xs text-secondary">
                      Type
                    </label>
                    <select
                      id={`prompt-var-type-${v.name}`}
                      value={v.type}
                      onChange={(e) =>
                        updateVariable(i, "type", e.target.value)
                      }
                      className="form-select w-full text-sm"
                    >
                      <option value="string">String</option>
                      <option value="enum">Enum</option>
                      <option value="number">Number</option>
                    </select>
                  </div>

                  {/* Default */}
                  <div>
                    <label htmlFor={`prompt-var-default-${v.name}`} className="text-xs text-secondary">
                      Default
                    </label>
                    <input
                      id={`prompt-var-default-${v.name}`}
                      type="text"
                      value={v.default || ""}
                      onChange={(e) =>
                        updateVariable(i, "default", e.target.value || null)
                      }
                      className="form-input w-full text-sm"
                      placeholder="(none)"
                    />
                  </div>
                </div>

                {/* Required checkbox - flipping this on makes the variable a
                    required form field at run time AND causes Prompt.assemble()
                    on the API to raise if the value is empty. Defaults to off
                    so existing optional-variable semantics (chunk drops when
                    empty) are preserved. */}
                <div className="mt-2 flex items-center gap-2">
                  <input
                    id={`prompt-var-required-${v.name}`}
                    type="checkbox"
                    checked={!!v.required}
                    onChange={(e) => updateVariable(i, "required", e.target.checked)}
                    className="form-checkbox"
                  />
                  <label
                    htmlFor={`prompt-var-required-${v.name}`}
                    className="text-xs text-secondary"
                  >
                    Required
                  </label>
                </div>

                {/* Options (for enum type) */}
                {v.type === "enum" && (
                  <div className="mt-2">
                    <label htmlFor={`prompt-var-options-${v.name}`} className="text-xs text-secondary">
                      Options (comma-separated)
                    </label>
                    <input
                      id={`prompt-var-options-${v.name}`}
                      type="text"
                      value={
                        optionsText[i] !== undefined
                          ? optionsText[i]
                          : (v.options || []).join(", ")
                      }
                      onChange={(e) =>
                        setOptionsText((prev) => ({
                          ...prev,
                          [i]: e.target.value,
                        }))
                      }
                      onBlur={() => {
                        const raw = optionsText[i];
                        if (raw !== undefined) {
                          updateVariable(
                            i,
                            "options",
                            raw
                              .split(",")
                              .map((s) => s.trim())
                              .filter(Boolean)
                          );
                          setOptionsText((prev) => {
                            const next = { ...prev };
                            delete next[i];
                            return next;
                          });
                        }
                      }}
                      className="form-input w-full text-sm"
                      placeholder="option1, option2, option3"
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Preview */}
      <div>
        <button
          type="button"
          onClick={() => setShowPreview(!showPreview)}
          className="text-sm font-medium text-info hover:underline"
        >
          {showPreview ? "Hide Preview" : "Show Preview"}
        </button>

        {showPreview && (
          <div className="mt-3 border border-primary rounded-lg p-4">
            {variables.length > 0 && (
              <div className="mb-4 space-y-2">
                <p className="text-xs font-medium text-secondary uppercase">
                  Sample Values
                </p>
                {variables.map((v) => (
                  <div key={v.name} className="flex items-center gap-2">
                    <label htmlFor={`prompt-preview-${v.name}`} className="text-sm text-secondary w-32 shrink-0">
                      {v.label}:
                    </label>
                    {v.type === "enum" && v.options?.length ? (
                      <select
                        id={`prompt-preview-${v.name}`}
                        value={previewValues[v.name] || ""}
                        onChange={(e) =>
                          setPreviewValues((prev) => ({
                            ...prev,
                            [v.name]: e.target.value,
                          }))
                        }
                        className="form-select text-sm flex-1"
                      >
                        <option value="">(empty - chunk excluded)</option>
                        {v.options.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={`prompt-preview-${v.name}`}
                        type="text"
                        value={previewValues[v.name] || ""}
                        onChange={(e) =>
                          setPreviewValues((prev) => ({
                            ...prev,
                            [v.name]: e.target.value,
                          }))
                        }
                        className="form-input text-sm flex-1"
                        placeholder="(empty - chunk excluded)"
                      />
                    )}
                  </div>
                ))}
              </div>
            )}
            <p className="text-xs font-medium text-secondary uppercase mb-1">
              Assembled Messages
            </p>
            <p className="text-xs text-muted mb-2">
              Preview shows variable substitution only. Jinja2 logic (if/else, filters) is rendered server-side.
            </p>
            {previewMessages.length === 0 ? (
              <p className="text-sm text-muted italic">(empty - no lines included)</p>
            ) : (
              <div className="space-y-2">
                {previewMessages.map((msg, i) => (
                  <div key={i} className="bg-surface rounded border border-primary overflow-hidden">
                    <div className={`px-2 py-0.5 text-xs font-mono uppercase ${ // css-check-ignore: no semantic token
                      msg.role === 'system' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300' :
                      msg.role === 'assistant' ? 'bg-success-subtle text-success' :
                      'bg-info-subtle text-info'
                    }`}>
                      {msg.role}
                    </div>
                    <pre className="text-sm whitespace-pre-wrap p-2 text-primary">
                      {msg.content}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Submit */}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="btn-primary"
        >
          {submitting ? "Saving..." : submitLabel}
        </button>
        <button
          type="button"
          onClick={() => window.history.back()}
          className="btn-secondary"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
