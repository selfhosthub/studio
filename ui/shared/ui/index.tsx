// ui/shared/ui/index.tsx

'use client';

import React from 'react';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  TableHeaderCell,
  TableContainer,
  StatusBadge,
  ActionButton,
  ActionLink,
  CustomSelect,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState
} from './Table';

export {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  TableHeaderCell,
  TableContainer,
  StatusBadge,
  ActionButton,
  ActionLink,
  CustomSelect,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState
};

export function Container({
  children, 
  className = "" 
}: { 
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div 
      className={`bg-card border border-primary text-primary${className ? ` ${className}` : ''}`}
    >
      {children}
    </div>
  );
}

export function Text({
  children, 
  variant = "primary",
  className = "" 
}: { 
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "tertiary" | "inverted";
  className?: string;
}) {
  const variantClasses = {
    primary: "text-primary",
    secondary: "text-secondary",
    tertiary: "text-muted",
    inverted: "text-inverted"
  };
  
  return (
    <span className={`${variantClasses[variant]}${className ? ` ${className}` : ''}`}>
      {children}
    </span>
  );
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
  className?: string;
}) {
  const variantClasses = {
    primary: "bg-blue-600 hover:bg-blue-700 text-white border-blue-600", // css-check-ignore: button variant, should use btn-primary class instead
    secondary: "bg-surface hover:bg-input text-primary border-primary",
    danger: "bg-red-600 hover:bg-red-700 text-white border-red-600" // css-check-ignore: button variant, should use btn-primary class instead
  };

  return (
    <button
      className={`px-4 py-2 rounded-md transition-colors ${variantClasses[variant]}${className ? ` ${className}` : ''}`}
      {...props}
    >
      {children}
    </button>
  );
}

/** Renders markdown-style links `[text](url)` inline. */
export function LinkedText({
  text,
  className = "",
  linkClassName = "text-info hover:underline",
}: {
  text: string;
  className?: string;
  linkClassName?: string;
}) {
  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match;
  let key = 0;

  while ((match = linkRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const [, linkText, url] = match;
    parts.push(
      <a
        key={key++}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={linkClassName}
      >
        {linkText}
      </a>
    );

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  if (parts.length === 0) {
    return <span className={className}>{text}</span>;
  }

  return <span className={className}>{parts}</span>;
}

export { ResourceTable } from './ResourceTable';
export type {
  ResourceTableProps,
  ColumnConfig as ResourceColumnConfig,
  SearchConfig,
  FilterConfig,
  SortConfig,
  PaginationConfig,
  ActionConfig,
  EmptyConfig,
} from './ResourceTable';

export { Modal } from './Modal';

export { ErrorBoundary } from './ErrorBoundary';

export { OutputViewRenderer } from './OutputViewRenderer';
export type { OutputViewConfig, ColumnConfig, FieldConfig } from './OutputViewRenderer';
export { TableOutputView } from './TableOutputView';
export { KeyValueOutputView } from './KeyValueOutputView';
export { JsonOutputView } from './JsonOutputView';