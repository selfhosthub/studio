// ui/app/(authenticated)/ai-prompts/prompts/components/PromptForm.tsx

"use client";

import { useMemo, useState } from "react";
import type {
  PromptChunk,
  PromptVariable,
} from "@/shared/types/prompt";
import { promptCategoryOptions } from "@/shared/lib/prompt-labels";
import HighlightTextarea from "./HighlightTextarea";

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
// Helpers
// ============================================================================

/** Built-in variables injected by the server - exclude from user-defined variables. */
const BUILTIN_VARIABLES = new Set(["today_date", "today_datetime"]);

/** Extract unique {{ variable_name }} references from prompt text.
 *  Tolerates Jinja2 filters ({{ x | filter }}, {{ x|filter1|filter2 }}) and
 *  ignores {% ... %} tags and built-in variables. */
const VARIABLE_REF_RE = /\{\{\s*(\w+)(?:\s*\|[^}]*)?\s*\}\}/g;

/** Allowed variable name: the characters VARIABLE_REF_RE captures. */
const VARIABLE_NAME_RE = /^\w+$/;

/** Default label derived from a variable name: "scene_count" -> "Scene Count". */
function autoLabel(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Matches every {{ name }} reference, filters included. */
function variableRefPattern(name: string): RegExp {
  return new RegExp(`\\{\\{\\s*${name}(?:\\s*\\|[^}]*)?\\s*\\}\\}`, "g");
}

/** Rewrites every {{ oldName }} reference to {{ newName }}, keeping spacing and filters. */
export function renameVariableRefs(text: string, oldName: string, newName: string): string {
  const re = new RegExp(`(\\{\\{\\s*)${oldName}(?=(?:\\s*\\|[^}]*)?\\s*\\}\\})`, "g");
  return text.replace(re, `$1${newName}`);
}

/** Returns why a rename is not allowed, or null when it is. */
export function validateVariableName(
  next: string,
  current: string,
  names: string[]
): string | null {
  if (!VARIABLE_NAME_RE.test(next)) return "Use letters, numbers and underscores only";
  if (BUILTIN_VARIABLES.has(next)) return `${next} is a built-in variable`;
  if (next !== current && names.includes(next)) return `A variable named ${next} already exists`;
  return null;
}

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

// Only conversation roles parse in the Messages box. System content has
// exactly one home (the System field) - see SYSTEM_LINE_RE below.
const ROLE_PREFIX_RE = /^\[(user|assistant)\]\s*/i;

/** A line-leading [system] tag in the Messages box. Rejected (never coerced):
 *  the domain model enforces "at most one system chunk, must be leading", so
 *  surface the violation inline instead of letting the save 400. */
const SYSTEM_LINE_RE = /^\s*\[system\]/im;

/** Convert Messages-box text into ordered chunks, parsing [user]/[assistant]
 *  prefixes. Blank lines (double newline) separate chunks; lines within a
 *  chunk are joined by \n. orderOffset shifts orders past the system chunk. */
function textToChunks(text: string, orderOffset: number): PromptChunk[] {
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
      order: index + orderOffset,
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
      const role = c.role || "user"; // defaults-ok
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

/** Split persisted chunks into the two-box view: the leading system chunk
 *  (the domain invariant guarantees at most one, first) feeds the System box;
 *  everything else feeds the Messages box. A legacy non-leading system chunk
 *  falls through to the Messages box as a literal [system] tag, where the
 *  inline rejection forces the author to fix it. */
function splitInitialChunks(chunks: PromptChunk[]): {
  system: string;
  messages: string;
} {
  const sorted = [...chunks].sort((a, b) => a.order - b.order);
  if (sorted.length > 0 && (sorted[0].role || "user") === "system") { // defaults-ok
    return { system: sorted[0].text, messages: chunksToText(sorted.slice(1)) };
  }
  return { system: "", messages: chunksToText(sorted) };
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

    // The composed-chunks memo (the only producer of `chunks` here) always
    // assigns a role, so chunk.role is non-null at this point. Type is loose
    // because PromptChunk is shared with backend payloads that may carry null.
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
  const initialSplit = useMemo(
    () => splitInitialChunks(initialData?.chunks || []),
    // initialData is a mount-time snapshot; matching the previous
    // useState(initialData?...) initializer semantics.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const [name, setName] = useState(initialData?.name || "");
  const [description, setDescription] = useState(
    initialData?.description || ""
  );
  const [category, setCategory] = useState(
    initialData?.category || "general" // defaults-ok
  );
  const [systemText, setSystemText] = useState(initialSplit.system);
  const [messagesText, setMessagesText] = useState(initialSplit.messages);
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

  // Variable rename: in-progress name edits, the focused variable, the last
  // rename's snapshot for Undo, and a rejected rename's message.
  const [nameDrafts, setNameDrafts] = useState<Record<string, string>>({});
  const [focusedVar, setFocusedVar] = useState<string | null>(null);
  const [lastRename, setLastRename] = useState<{
    from: string;
    to: string;
    systemText: string;
    messagesText: string;
    variables: PromptVariable[];
  } | null>(null);
  const [renameError, setRenameError] = useState<{ name: string; message: string } | null>(null);

  const categoryOptions = useMemo(
    () => promptCategoryOptions(initialData?.category ? [initialData.category] : []),
    // initialData is a mount-time snapshot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const highlight = useMemo(
    () => (focusedVar ? variableRefPattern(focusedVar) : null),
    [focusedVar]
  );

  // [system] typed in the Messages box - rejected inline, never coerced.
  const systemInMessages = useMemo(
    () => SYSTEM_LINE_RE.test(messagesText),
    [messagesText]
  );

  // Auto-detect variables across both boxes
  const detectedVarNames = useMemo(
    () => detectVariables(systemText + "\n" + messagesText),
    [systemText, messagesText]
  );

  // Sync detected variables with the variables list (adjust during render, not in
  // an effect) whenever the detected-name set changes. detectedVarNames is memoized.
  const [prevDetectedVarNames, setPrevDetectedVarNames] = useState(detectedVarNames);
  if (detectedVarNames !== prevDetectedVarNames) {
    setPrevDetectedVarNames(detectedVarNames);
    setVariables((prev) => {
      // Keep existing variables that are still detected, add new ones
      const existing = new Map(prev.map((v) => [v.name, v]));
      const detected = new Set(detectedVarNames);
      const removed = prev.filter((v) => !detected.has(v.name));
      const added = detectedVarNames.filter((name) => !existing.has(name));
      // One name swapped for another in the text is a rename: carry its settings.
      if (removed.length === 1 && added.length === 1) {
        const [from] = removed;
        existing.set(added[0], {
          ...from,
          name: added[0],
          label: from.label === autoLabel(from.name) ? autoLabel(added[0]) : from.label,
        });
      }
      return detectedVarNames.map(
        (name) =>
          existing.get(name) || {
            name,
            label: autoLabel(name),
            type: "string",
            options: null,
            default: null,
            required: false,
          }
      );
    });
  }

  // Initialize preview values from variable defaults whenever the variables list
  // changes (adjust during render, not in an effect).
  const [prevVariables, setPrevVariables] = useState(variables);
  if (variables !== prevVariables) {
    setPrevVariables(variables);
    setPreviewValues((prev) => {
      const next = { ...prev };
      for (const v of variables) {
        const prevDefault = prevVariables.find((p) => p.name === v.name)?.default || "";
        // Seed new keys, and follow a changed default while the value still holds the old one
        if (!(v.name in next) || next[v.name] === prevDefault) {
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
  }

  // Recompose the two boxes into the persisted chunks[] view: System box ⇄
  // the single leading system chunk, Messages box ⇄ the user/assistant chunks.
  const chunks = useMemo(() => {
    const hasSystem = systemText.trim().length > 0;
    const messageChunks = textToChunks(messagesText, hasSystem ? 1 : 0);
    if (!hasSystem) return messageChunks;
    const varMatch = systemText.match(new RegExp(VARIABLE_REF_RE.source));
    const systemChunk: PromptChunk = {
      text: systemText,
      variable: varMatch ? varMatch[1] : null,
      order: 0,
      role: "system",
    };
    return [systemChunk, ...messageChunks];
  }, [systemText, messagesText]);

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

  const editSystemText = (value: string) => {
    setSystemText(value);
    setLastRename(null);
  };

  const editMessagesText = (value: string) => {
    setMessagesText(value);
    setLastRename(null);
  };

  const clearDraft = (name: string) =>
    setNameDrafts((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });

  /** Applies the drafted name for `oldName`. Returns the name in effect afterwards,
   *  or null when the draft is invalid and nothing changed. */
  const commitRename = (oldName: string): string | null => {
    const draft = nameDrafts[oldName];
    if (draft === undefined) return oldName;
    const next = draft.trim();
    if (next === oldName) {
      clearDraft(oldName);
      return oldName;
    }
    const problem = validateVariableName(
      next,
      oldName,
      variables.map((v) => v.name)
    );
    if (problem) {
      setRenameError({ name: oldName, message: problem });
      return null;
    }
    setLastRename({ from: oldName, to: next, systemText, messagesText, variables });
    setVariables((prev) =>
      prev.map((v) =>
        v.name === oldName
          ? {
              ...v,
              name: next,
              label: v.label === autoLabel(oldName) ? autoLabel(next) : v.label,
            }
          : v
      )
    );
    setPreviewValues((prev) => {
      const carried = { ...prev, [next]: prev[oldName] ?? "" };
      delete carried[oldName];
      return carried;
    });
    setSystemText((t) => renameVariableRefs(t, oldName, next));
    setMessagesText((t) => renameVariableRefs(t, oldName, next));
    clearDraft(oldName);
    setRenameError(null);
    return next;
  };

  const undoRename = () => {
    if (!lastRename) return;
    setSystemText(lastRename.systemText);
    setMessagesText(lastRename.messagesText);
    setVariables(lastRename.variables);
    setLastRename(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (systemInMessages) {
      setError("System content belongs in the System field");
      return;
    }
    if (!messagesText.trim()) {
      setError("Messages are required");
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
      setError(err instanceof Error ? err.message : "Failed to save prompt");
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
          placeholder="Brief description of what this prompt does"
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
          {categoryOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* System */}
      <div>
        <label htmlFor="systemText" className="form-label">
          System
        </label>
        <p className="text-xs text-secondary mb-1">
          Standing instructions - persona, rules, output format. Sent in the
          provider&apos;s system slot regardless of provider. Optional.
          Jinja2 works here too: <code className="bg-card px-1 rounded">{"{{ variable }}"}</code>,{" "}
          <code className="bg-card px-1 rounded">{"{% if %}"}</code>, filters,{" "}
          <code className="bg-card px-1 rounded">{"{{ today_date }}"}</code>.
        </p>
        <HighlightTextarea
          id="systemText"
          value={systemText}
          onChange={editSystemText}
          highlight={highlight}
          className="form-textarea w-full font-mono text-sm"
          rows={4}
          placeholder="You are a scriptwriter who turns articles into narrated stories."
        />
      </div>

      {/* Messages */}
      <div>
        <label htmlFor="messagesText" className="form-label">
          Messages <span className="text-danger">*</span>
        </label>
        <p className="text-xs text-secondary mb-1">
          The conversation turns. Prefix blocks with{" "}
          <code className="bg-card px-1 rounded">[user]</code> or{" "}
          <code className="bg-card px-1 rounded">[assistant]</code> (e.g. few-shot
          examples); blocks without a prefix inherit the previous role
          (default: user). Blank lines separate messages.
        </p>
        <HighlightTextarea
          id="messagesText"
          value={messagesText}
          onChange={editMessagesText}
          highlight={highlight}
          className="form-textarea w-full font-mono text-sm"
          rows={10}
          placeholder={`[user] Write a narrated story based on the article below.\nStyle: {{ style }}.\nStructure it as {{ scene_count }} scenes.`}
          required
        />
        {systemInMessages && (
          <p className="text-xs text-danger mt-1">
            System content belongs in the System field - remove the{" "}
            <code className="bg-card px-1 rounded">[system]</code> tag from
            Messages.
          </p>
        )}
      </div>

      {/* Detected Variables */}
      {variables.length > 0 && (
        <div>
          <h3 className="form-label mb-2">
            Variables ({variables.length})
          </h3>
          {lastRename && (
            <p className="text-xs text-secondary mb-2" role="status">
              Renamed <code className="bg-card px-1 rounded">{lastRename.from}</code> to{" "}
              <code className="bg-card px-1 rounded">{lastRename.to}</code>.{" "}
              <button
                type="button"
                onClick={undoRename}
                className="text-info hover:underline"
              >
                Undo
              </button>
            </p>
          )}
          <div className="space-y-3">
            {variables.map((v, i) => (
              <div
                key={i}
                className="border border-primary rounded-lg p-3"
              >
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  {/* Name: renames every {{ name }} reference on blur or Enter */}
                  <div>
                    <label htmlFor={`prompt-var-name-${v.name}`} className="text-xs text-secondary">
                      Name
                    </label>
                    <input
                      id={`prompt-var-name-${v.name}`}
                      type="text"
                      value={nameDrafts[v.name] ?? v.name}
                      onFocus={() => {
                        setFocusedVar(v.name);
                        setRenameError(null);
                      }}
                      onChange={(e) => {
                        const value = e.target.value;
                        setNameDrafts((prev) => ({ ...prev, [v.name]: value }));
                        setRenameError(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          const name = commitRename(v.name);
                          if (name) setFocusedVar(name);
                        } else if (e.key === "Escape") {
                          clearDraft(v.name);
                          setRenameError(null);
                        }
                      }}
                      onBlur={() => {
                        if (commitRename(v.name) === null) clearDraft(v.name);
                        setFocusedVar(null);
                      }}
                      aria-invalid={renameError?.name === v.name}
                      aria-describedby={
                        renameError?.name === v.name ? `prompt-var-name-error-${v.name}` : undefined
                      }
                      className="form-input w-full text-sm font-mono"
                    />
                    {renameError?.name === v.name && (
                      <p
                        id={`prompt-var-name-error-${v.name}`}
                        className="text-xs text-danger mt-1"
                      >
                        {renameError.message}
                      </p>
                    )}
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
                        <option value="">(empty, so this message is left out)</option>
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
                        placeholder="(empty, so this message is left out)"
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
          className="btn-cancel text-sm inline-flex items-center"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
