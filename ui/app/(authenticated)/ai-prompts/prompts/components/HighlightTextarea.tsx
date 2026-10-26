// ui/app/(authenticated)/ai-prompts/prompts/components/HighlightTextarea.tsx

"use client";

import { useEffect, useMemo, useRef } from "react";

interface Props extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "onChange"> {
  value: string;
  onChange: (value: string) => void;
  highlight: RegExp | null;
}

interface Segment {
  text: string;
  marked: boolean;
}

// Splits text into plain and matched runs for the given pattern.
export function splitHighlights(text: string, pattern: RegExp | null): Segment[] {
  if (!pattern) return [{ text, marked: false }];
  const regex = new RegExp(pattern.source, "g");
  const segments: Segment[] = [];
  let last = 0;
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) segments.push({ text: text.slice(last, match.index), marked: false });
    segments.push({ text: match[0], marked: true });
    last = match.index + match[0].length;
  }
  if (last < text.length) segments.push({ text: text.slice(last), marked: false });
  return segments;
}

// Textarea that marks every match of `highlight` and scrolls the first one into view.
export default function HighlightTextarea({ value, onChange, highlight, className = "", ...rest }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  const segments = useMemo(() => splitHighlights(value, highlight), [value, highlight]);
  const hasMatch = segments.some((s) => s.marked);

  // Scroll the first marked occurrence into view inside the textarea and on the page.
  useEffect(() => {
    const textarea = textareaRef.current;
    const backdrop = backdropRef.current;
    if (!hasMatch || !textarea || !backdrop) return;
    const mark = backdrop.querySelector("mark");
    if (!mark) return;
    textarea.scrollTop = Math.max(0, mark.offsetTop - textarea.clientHeight / 3);
    backdrop.scrollTop = textarea.scrollTop;
    textarea.scrollIntoView?.({ block: "nearest" });
  }, [hasMatch, highlight]);

  const syncScroll = () => {
    if (backdropRef.current && textareaRef.current) {
      backdropRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  };

  return (
    <div className="relative">
      {hasMatch && (
        <div
          ref={backdropRef}
          aria-hidden="true"
          data-testid={rest.id ? `${rest.id}-highlights` : undefined}
          className={`${className} form-textarea-backdrop absolute inset-0`}
        >
          {segments.map((s, i) =>
            s.marked ? (
              <mark key={i} className="bg-warning-subtle rounded-sm">
                {s.text}
              </mark>
            ) : (
              <span key={i}>{s.text}</span>
            ),
          )}
          {"\n"}
        </div>
      )}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={syncScroll}
        className={`${className} relative${hasMatch ? " form-textarea-overlay" : ""}`}
        {...rest}
      />
    </div>
  );
}
