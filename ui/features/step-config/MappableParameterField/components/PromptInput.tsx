// ui/features/step-config/MappableParameterField/components/PromptInput.tsx

'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Link2, Type } from 'lucide-react';
import { getPrompts } from '@/shared/api';
import { getEffectiveOutputs } from '@/shared/lib/step-utils';
import type {
  Prompt,
  PromptChunk,
  PromptVariable,
} from '@/shared/types/prompt';
import type { Step } from '@/entities/workflow';

interface PromptInputProps {
  promptId: string;
  promptSlug?: string;
  variableValues: Record<string, string>;
  onPromptChange: (promptId: string, variableValues?: Record<string, string>) => void;
  onVariableValuesChange: (values: Record<string, string>) => void;
  previousSteps?: Step[];
}

interface AssembledMessage {
  role: string;
  content: string;
}

/** Check if a value is a {{ step.field }} mapping expression */
function isMappedExpression(value: string): boolean {
  return /^\{\{\s*\w+\.\w+(\[\*\]\.\w+)?\s*\}\}$/.test(value);
}

/** Parse {{ step_id.field }} into parts. Handles partial expressions (step selected, no field yet). */
function parseMappingExpression(value: string): { stepId: string; field: string } | null {
  const match = value.match(/^\{\{\s*(\w+)\.?(.*?)\s*\}\}$/);
  if (!match) return null;
  return { stepId: match[1], field: match[2] };
}

/** Assemble preview as messages array (mirrors backend logic). */
function assemblePreview(
  chunks: PromptChunk[],
  variableValues: Record<string, string>
): AssembledMessage[] {
  const sorted = [...chunks].sort((a, b) => a.order - b.order);
  const messages: AssembledMessage[] = [];

  for (const chunk of sorted) {
    if (chunk.variable) {
      const value = variableValues[chunk.variable] || '';
      if (!value) continue;
    }

    const text = chunk.text.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, varName) => {
      return variableValues[varName] ?? match;
    });

    const role = chunk.role || 'user';
    if (messages.length > 0 && messages[messages.length - 1].role === role) {
      messages[messages.length - 1].content += '\n\n' + text;
    } else {
      messages.push({ role, content: text });
    }
  }

  return messages;
}

export function PromptInput({
  promptId,
  promptSlug,
  variableValues,
  onPromptChange,
  onVariableValuesChange,
  previousSteps = [],
}: PromptInputProps) {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPreview, setShowPreview] = useState(false);
  const [dragOverVar, setDragOverVar] = useState<string | null>(null);
  const [mappedVars, setMappedVars] = useState<Set<string>>(new Set());

  // Fetch prompts once on mount
  useEffect(() => {
    getPrompts()
      .then((data) => setPrompts(data.filter((t) => t.is_enabled)))
      .catch(() => setPrompts([]))
      .finally(() => setLoading(false));
  }, []);

  const selectedPrompt = useMemo(
    () => prompts.find((t) => t.id === promptId) ?? null,
    [prompts, promptId]
  );

  // Auto-resolve promptSlug → promptId when the prompt was installed after
  // the workflow was copied (promptId is empty but promptSlug matches an
  // installed prompt's marketplace_slug).
  useEffect(() => {
    if (promptId || !promptSlug || loading || prompts.length === 0) return;
    const match = prompts.find(p => p.marketplace_slug === promptSlug);
    if (match) {
      onPromptChange(match.id);
    }
  }, [promptId, promptSlug, loading, prompts, onPromptChange]);

  // Auto-apply template defaults for variables that have no saved value.
  // handleTemplateSelect does this when the user picks a template, but on
  // initial load (e.g. from seeder data) variableValues may be empty.
  useEffect(() => {
    if (!selectedPrompt) return;
    const defaults: Record<string, string> = {};
    let needsUpdate = false;
    for (const v of selectedPrompt.variables) {
      const existing = variableValues[v.name];
      if (existing !== undefined && existing !== '') {
        defaults[v.name] = existing;
      } else if (v.default) {
        defaults[v.name] = v.default;
        needsUpdate = true;
      } else {
        defaults[v.name] = '';
      }
    }
    if (needsUpdate) {
      onVariableValuesChange(defaults);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only run when template loads
  }, [selectedPrompt]);

  // When prompt changes, send promptId + variable defaults in one call
  const handlePromptSelect = (id: string) => {
    const tpl = prompts.find((t) => t.id === id);
    const defaults: Record<string, string> = {};
    if (tpl) {
      for (const v of tpl.variables) {
        defaults[v.name] = variableValues[v.name] ?? v.default ?? '';
      }
    }
    onPromptChange(id, defaults);
  };

  const handleVariableChange = (name: string, value: string) => {
    onVariableValuesChange({ ...variableValues, [name]: value });
  };

  const previewMessages = useMemo(() => {
    if (!selectedPrompt) return [];
    return assemblePreview(selectedPrompt.chunks, variableValues);
  }, [selectedPrompt, variableValues]);

  // Group prompts by category for the dropdown
  const groupedPrompts = useMemo(() => {
    const groups: Record<string, Prompt[]> = {};
    for (const t of prompts) {
      const cat = t.category || 'general';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(t);
    }
    return groups;
  }, [prompts]);

  const reversedSteps = useMemo(() => [...previousSteps].reverse(), [previousSteps]);

  const handleVarDragOver = (e: React.DragEvent, varName: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes('application/x-field-mapping')) {
      e.dataTransfer.dropEffect = 'copy';
      setDragOverVar(varName);
    }
  };

  const handleVarDrop = (e: React.DragEvent, varName: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverVar(null);
    const rawData = e.dataTransfer.getData('application/x-field-mapping');
    if (!rawData) return;
    try {
      const { stepId, fieldName } = JSON.parse(rawData);
      handleVariableChange(varName, `{{ ${stepId}.${fieldName} }}`);
    } catch (err) {
      console.error('Failed to parse drag data:', err);
    }
  };

  const handleVarDragLeave = (e: React.DragEvent) => {
    e.stopPropagation();
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setDragOverVar(null);
    }
  };

  const renderVariableField = (v: PromptVariable) => {
    const currentValue = variableValues[v.name] || '';
    const isMapped = mappedVars.has(v.name) || isMappedExpression(currentValue);
    const parsed = isMapped ? parseMappingExpression(currentValue) : null;
    const isInstanceForm = parsed?.stepId === '__instance_form__';
    const hasMappingSources = previousSteps.length > 0 || isInstanceForm;

    // Get outputs for the currently selected step (in mapped mode)
    const selectedStep = parsed && !isInstanceForm ? previousSteps.find(s => s.id === parsed.stepId) : null;
    const availableOutputs = selectedStep ? getEffectiveOutputs(selectedStep, previousSteps) : {};
    const isDragTarget = dragOverVar === v.name;

    return (
      <div
        key={v.name}
        className={`space-y-1 rounded p-1 transition-colors ${
          isDragTarget
            ? 'ring-2 ring-critical bg-critical-subtle'
            : ''
        }`}
        onDragOver={(e) => handleVarDragOver(e, v.name)}
        onDrop={(e) => handleVarDrop(e, v.name)}
        onDragLeave={handleVarDragLeave}
      >
        <div className="flex items-center justify-between">
          <label className="text-xs text-secondary truncate" title={v.label}>
            {v.label}:
          </label>
          {hasMappingSources && (
            <button
              type="button"
              onClick={() => {
                if (isMapped) {
                  // Switch to static - clear the expression and mapped state
                  setMappedVars(prev => { const next = new Set(prev); next.delete(v.name); return next; });
                  handleVariableChange(v.name, v.default ?? '');
                } else {
                  // Switch to mapped - show empty dropdowns
                  setMappedVars(prev => new Set(prev).add(v.name));
                }
              }}
              className={`flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded-full transition-colors ${
                isMapped
                  ? 'bg-critical-subtle text-critical border border-critical'
                  : 'bg-card text-secondary border border-primary hover:bg-input'
              }`}
            >
              {isMapped ? <><Link2 className="h-2.5 w-2.5" /><span>Mapped</span></> : <><Type className="h-2.5 w-2.5" /><span>Static</span></>}
            </button>
          )}
        </div>

        {isMapped ? (
          <div className="flex gap-2">
            <select
              value={parsed?.stepId || ''}
              onChange={(e) => {
                const stepId = e.target.value;
                if (!stepId) return;
                if (stepId === '__instance_form__') {
                  handleVariableChange(v.name, `{{ __instance_form__. }}`);
                  return;
                }
                handleVariableChange(v.name, `{{ ${stepId}. }}`);
              }}
              className="flex-1 min-w-0 p-1.5 border rounded text-xs"
            >
              <option value="">Select step...</option>
              {isInstanceForm && (
                <option value="__instance_form__">Instance Form</option>
              )}
              {reversedSteps.map((step) => (
                <option key={step.id} value={step.id}>{step.name || step.id}</option>
              ))}
            </select>
            <select
              value={parsed?.field || ''}
              onChange={(e) => {
                if (!parsed?.stepId || !e.target.value) return;
                handleVariableChange(v.name, `{{ ${parsed.stepId}.${e.target.value} }}`);
              }}
              disabled={!parsed?.stepId}
              className="flex-1 min-w-0 p-1.5 border rounded text-xs disabled:opacity-50"
            >
              <option value="">Select output...</option>
              {isInstanceForm && parsed?.field ? (
                <option value={parsed.field}>{parsed.field} (string)</option>
              ) : Object.entries(availableOutputs).flatMap(([fieldName, fieldDef]) => {
                const typedField = fieldDef as { type?: string; items?: { properties?: Record<string, { type?: string }> } };
                const options = [
                  <option key={fieldName} value={fieldName}>{fieldName} ({typedField.type || 'string'})</option>
                ];
                if (typedField.type === 'array' && typedField.items?.properties) {
                  Object.entries(typedField.items.properties).forEach(([nestedKey, nestedDef]) => {
                    const nestedPath = `${fieldName}[*].${nestedKey}`;
                    options.push(<option key={nestedPath} value={nestedPath}>&nbsp;&nbsp;↳ {nestedKey} ({nestedDef.type || 'string'})</option>);
                  });
                }
                return options;
              })}
            </select>
          </div>
        ) : (
          // Static mode - existing behavior
          v.type === 'enum' && v.options?.length ? (
            <select
              value={currentValue}
              onChange={(e) => handleVariableChange(v.name, e.target.value)}
              className="form-select text-sm w-full"
            >
              <option value="">(empty - line excluded)</option>
              {v.options.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          ) : v.type === 'number' ? (
            <input
              type="number"
              value={currentValue}
              onChange={(e) => handleVariableChange(v.name, e.target.value)}
              className="form-input text-sm w-full"
              placeholder={v.default || '(empty - line excluded)'}
            />
          ) : (
            <textarea
              value={currentValue}
              onChange={(e) => handleVariableChange(v.name, e.target.value)}
              className="form-textarea text-sm w-full"
              rows={3}
              placeholder={v.default || '(empty - line excluded)'}
            />
          )
        )}
      </div>
    );
  };

  return (
    <div className="flex-1 min-w-0 space-y-3">
      {/* Prompt selector */}
      <select
        value={promptId}
        onChange={(e) => handlePromptSelect(e.target.value)}
        className="form-select w-full text-sm"
        disabled={loading}
      >
        <option value="">
          {loading ? 'Loading prompts...' : 'Select a prompt...'}
        </option>
        {Object.entries(groupedPrompts).map(([category, tpls]) => (
          <optgroup
            key={category}
            label={category.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
          >
            {tpls.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>

      {/* Variable inputs */}
      {selectedPrompt && selectedPrompt.variables.length > 0 && (
        <div className="space-y-2 pl-1">
          {selectedPrompt.variables.map(renderVariableField)}
        </div>
      )}

      {/* Preview toggle */}
      {selectedPrompt && (
        <div>
          <button
            type="button"
            onClick={() => setShowPreview(!showPreview)}
            className="inline-flex items-center gap-1 text-xs text-secondary hover:text-secondary"
          >
            {showPreview ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Preview
          </button>
          {showPreview && (
            <div className="mt-1 max-h-48 overflow-y-auto">
              {previewMessages.length === 0 ? (
                <p className="text-xs text-muted italic">(empty - no lines included)</p>
              ) : (
                <div className="space-y-1">
                  {previewMessages.map((msg, i) => (
                    <div key={i} className="bg-surface rounded border border-primary overflow-hidden">
                      <div className={`px-1.5 py-0.5 text-[10px] font-mono uppercase ${
                        msg.role === 'system' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300' : // css-check-ignore: no semantic token
                        msg.role === 'assistant' ? 'bg-success-subtle text-success' :
                        'bg-info-subtle text-info'
                      }`}>
                        {msg.role}
                      </div>
                      <pre className="text-xs whitespace-pre-wrap p-1.5 text-secondary">
                        {msg.content}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default PromptInput;
