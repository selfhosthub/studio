// ui/shared/ui/Table.tsx

import React from 'react';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';

interface TableProps {
  children: React.ReactNode;
  className?: string;
}

export function Table({ children, className = '' }: TableProps) {
  return (
    <div className="overflow-x-auto">
      <table className={`data-table ${className}`}>
        {children}
      </table>
    </div>
  );
}

interface TableHeaderProps {
  children: React.ReactNode;
  className?: string;
}

export function TableHeader({ children, className = '' }: TableHeaderProps) {
  return (
    <thead className={`table-header ${className}`}>
      {children}
    </thead>
  );
}

interface TableBodyProps {
  children: React.ReactNode;
  className?: string;
}

export function TableBody({ children, className = '' }: TableBodyProps) {
  return (
    <tbody className={`table-body ${className}`}>
      {children}
    </tbody>
  );
}

interface TableRowProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  selected?: boolean;
}

export function TableRow({ children, className = '', onClick, selected }: TableRowProps) {
  return (
    <tr
      className={`table-row ${selected ? 'table-row-selected' : ''} ${onClick ? 'cursor-pointer' : ''} ${className}`}
      onClick={onClick}
    >
      {children}
    </tr>
  );
}

export interface TableCellProps {
  children: React.ReactNode;
  className?: string;
  align?: 'left' | 'center' | 'right';
  colSpan?: number;
}

export function TableCell({
  children,
  className = '',
  align = 'left',
  colSpan
}: TableCellProps) {
  const alignmentClass = {
    'left': 'text-left',
    'center': 'text-center',
    'right': 'text-right'
  };

  return (
    <td
      className={`table-cell ${alignmentClass[align]} ${className}`}
      colSpan={colSpan}
    >
      {children}
    </td>
  );
}

interface TableHeaderCellProps {
  children: React.ReactNode;
  className?: string;
  align?: 'left' | 'center' | 'right';
  onClick?: () => void;
}

export function TableHeaderCell({
  children,
  className = '',
  align = 'left',
  onClick
}: TableHeaderCellProps) {
  const alignmentClass = {
    'left': 'text-left',
    'center': 'text-center',
    'right': 'text-right'
  };

  return (
    <th
      className={`table-header-cell ${alignmentClass[align]} ${onClick ? 'cursor-pointer hover:bg-input' : ''} ${className}`}
      onClick={onClick}
    >
      {children}
    </th>
  );
}

interface StatusBadgeProps {
  status: string;
  variant?: 'success' | 'warning' | 'error' | 'info' | 'default';
  className?: string;
}

// Map status values to variants for automatic color selection
function getVariantFromStatus(status: string): 'success' | 'warning' | 'error' | 'info' | 'default' {
  const statusLower = status.toLowerCase();
  switch (statusLower) {
    case 'completed':
    case 'active':
    case 'success':
      return 'success';
    case 'running':
    case 'processing':
    case 'in_progress':
    case 'queued':
      // 'queued' uses the same in-flight color family as running - the step
      // is claimed (or about to be) by a worker, just not actively executing
      // yet. The label distinguishes "queued" vs "running"; the color
      // distinguishes "in flight" vs "waiting" / "terminal".
      return 'info';
    case 'pending':
    case 'waiting':
    case 'waiting_for_approval':
    case 'waiting_for_manual_trigger':
      return 'warning';
    case 'failed':
    case 'error':
    case 'cancelled':
    case 'timeout':
    case 'stopped':
      return 'error';
    default:
      return 'default';
  }
}

export function StatusBadge({
  status,
  variant,
  className = ''
}: StatusBadgeProps) {
  // Auto-detect variant from status if not explicitly provided
  const effectiveVariant = variant ?? getVariantFromStatus(status);

  const variantStyles = {
    success: 'badge-success',
    warning: 'badge-warning',
    error: 'badge-error',
    info: 'badge-info',
    default: 'badge-default'
  };

  return (
    <span className={`badge ${variantStyles[effectiveVariant]} ${className}`}>
      {status}
    </span>
  );
}

interface ActionButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: 'active' | 'passive' | 'destructive' | 'navigate' | 'warning' | 'change' | 'secondary' | 'danger';
  size?: 'sm' | 'md';
  className?: string;
  disabled?: boolean;
  title?: string;
}

export function ActionButton({
  children,
  onClick,
  variant = 'passive',
  size = 'sm',
  className = '',
  disabled = false
}: ActionButtonProps) {
  // Use centralized CSS classes from globals.css for consistent styling
  // Classes: action-btn-{variant} for sm, action-btn-{variant}-md for md
  const sizeModifier = size === 'md' ? '-md' : '';
  const cssClass = `action-btn-${variant}${sizeModifier}`;

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`${cssClass} ${disabled ? 'opacity-50 cursor-not-allowed' : ''} ${className}`}
    >
      {children}
    </button>
  );
}

interface ActionLinkProps {
  children: React.ReactNode;
  href: string;
  variant?: 'primary' | 'secondary' | 'danger';
  className?: string;
  onClick?: (e: React.MouseEvent<HTMLAnchorElement>) => void;
}

export function ActionLink({ 
  children, 
  href,
  variant = 'primary',
  className = '',
  onClick
}: ActionLinkProps) {
  const variantStyles = {
    primary: 'link',
    secondary: 'link-subtle',
    danger: 'link-danger'
  };
  
  return (
    <a 
      href={href} 
      className={`${variantStyles[variant]} text-sm font-medium ${className}`}
      onClick={onClick}
    >
      {children}
    </a>
  );
}

export function TableContainer({ children, className = '' }: { children: React.ReactNode, className?: string }) {
  return (
    <div className={`table-container mb-8 ${className}`}>
      <div className="p-0">
        {children}
      </div>
    </div>
  );
}

// ============================================
// List Display Components
// ============================================

// Search Input Component
interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function SearchInput({
  value,
  onChange,
  placeholder = "Search...",
  className = ""
}: SearchInputProps) {
  return (
    <div className={`relative w-full max-w-md ${className}`}>
      <svg
        className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted w-4 h-4"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.3-4.3" />
      </svg>
      <input
        type="text"
        placeholder={placeholder}
        className="form-input-search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

// Pagination Component
interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalCount: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: number[];
  itemLabel?: string;
  showPageSizeSelector?: boolean;
  position?: 'top' | 'bottom' | 'both';
}

const ChevronLeft = () => (
  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="m15 18-6-6 6-6" />
  </svg>
);

const ChevronRight = () => (
  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="m9 18 6-6-6-6" />
  </svg>
);

export function Pagination({
  currentPage,
  totalPages,
  totalCount,
  pageSize,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = PAGE_SIZE_OPTIONS,
  itemLabel = "item",
  showPageSizeSelector = true,
  position = 'bottom'
}: PaginationProps) {
  const hasPrevPage = currentPage > 1;
  const hasNextPage = currentPage < totalPages;

  const navButtonClass = `p-1.5 border border-primary rounded-md
    bg-card text-secondary
    hover:bg-surface disabled:opacity-50 disabled:cursor-not-allowed`;

  const selectClass = `px-2 py-1 border border-primary rounded-md
    bg-card text-secondary`;

  if (position === 'top') {
    return (
      <div className="flex items-center gap-4">
        {showPageSizeSelector && onPageSizeChange && (
          <div className="flex items-center gap-2">
            <span className="text-secondary">Show:</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className={selectClass}
            >
              {pageSizeOptions.map((size) => (
                <option key={size} value={size}>{size}</option>
              ))}
            </select>
          </div>
        )}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={!hasPrevPage}
            className={navButtonClass}
          >
            <ChevronLeft />
          </button>
          <select
            value={currentPage}
            onChange={(e) => onPageChange(Number(e.target.value))}
            className={selectClass}
          >
            {Array.from({ length: totalPages || 1 }, (_, i) => i + 1).map((page) => (
              <option key={page} value={page}>{page}</option>
            ))}
          </select>
          <span className="text-secondary">of {totalPages || 1}</span>
          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={!hasNextPage}
            className={navButtonClass}
          >
            <ChevronRight />
          </button>
        </div>
      </div>
    );
  }

  // Bottom pagination (default)
  return (
    <div className="flex items-center justify-between mt-4 py-3 border-t border-primary">
      <span className="text-secondary">
        {totalCount} {itemLabel}{totalCount === 1 ? '' : 's'}
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={!hasPrevPage}
          className={navButtonClass}
        >
          <ChevronLeft />
        </button>
        <select
          value={currentPage}
          onChange={(e) => onPageChange(Number(e.target.value))}
          className={selectClass}
        >
          {Array.from({ length: totalPages || 1 }, (_, i) => i + 1).map((page) => (
            <option key={page} value={page}>{page}</option>
          ))}
        </select>
        <span className="text-secondary">of {totalPages || 1}</span>
        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!hasNextPage}
          className={navButtonClass}
        >
          <ChevronRight />
        </button>
      </div>
    </div>
  );
}

// Loading State Component
interface LoadingStateProps {
  message?: string;
  className?: string;
}

export function LoadingState({
  message = "Loading...",
  className = ""
}: LoadingStateProps) {
  return (
    <div className={`flex items-center justify-center py-12 ${className}`} role="status" aria-live="polite">
      <div className="text-center">
        <div className="spinner-md"></div>
        <p className="mt-2 text-sm text-secondary">{message}</p>
      </div>
    </div>
  );
}

// Error State Component
interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

export function ErrorState({
  title = "Error",
  message,
  onRetry,
  retryLabel = "Retry",
  className = ""
}: ErrorStateProps) {
  return (
    <div className={`card alert-error ${className}`} role="alert" aria-live="assertive">
      <div className="flex items-start">
        <div className="flex-shrink-0">
          <svg className="h-5 w-5 text-danger" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
        </div>
        <div className="ml-3">
          <h3 className="text-sm font-medium alert-error-text">{title}</h3>
          <p className="mt-1 text-sm alert-error-text">{message}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 btn-danger text-sm"
            >
              {retryLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Empty State Component
interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className = ""
}: EmptyStateProps) {
  return (
    <div className={`text-center py-12 ${className}`}>
      {icon && (
        <div className="mx-auto h-12 w-12 text-muted mb-4">
          {icon}
        </div>
      )}
      <h3 className="mt-2 text-sm font-semibold text-primary">{title}</h3>
      {description && (
        <p className="mt-1 text-sm text-secondary">{description}</p>
      )}
      {action && (
        <div className="mt-6">{action}</div>
      )}
    </div>
  );
}

// ============================================
// Custom Select Component
// ============================================

// Custom Select component that works consistently on mobile
interface SelectOption {
  value: string;
  label: string;
}

interface CustomSelectProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  className?: string;
  placeholder?: string;
}

export function CustomSelect({
  id,
  value,
  onChange,
  options,
  className = '',
  placeholder
}: CustomSelectProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const selectRef = React.useRef<HTMLDivElement>(null);

  const selectedOption = options.find(opt => opt.value === value);

  // Close dropdown when clicking outside
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (selectRef.current && !selectRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close on escape key
  React.useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, []);

  return (
    <div ref={selectRef} className={`relative ${className}`}>
      <button
        type="button"
        id={id}
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between rounded-md border border-primary shadow-sm px-3 py-2 bg-surface text-primary text-base focus:ring-2 focus:border-transparent focus:outline-none min-h-[44px]"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className={selectedOption ? '' : 'text-muted'}>
          {selectedOption?.label || placeholder || 'Select...'}
        </span>
        <svg
          className={`h-5 w-5 text-muted transition-transform ${isOpen ? 'rotate-180' : ''}`}
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {isOpen && (
        <ul
          className="absolute z-50 mt-1 w-full bg-card shadow-lg max-h-60 rounded-md py-1 text-base ring-1 ring-black ring-opacity-5 overflow-auto focus:outline-none focus-visible:ring-2"
          role="listbox"
        >
          {options.map((option) => (
            <li
              key={option.value}
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
              className={`cursor-pointer select-none relative py-3 px-4 text-base ${
                option.value === value
                  ? 'bg-info-subtle text-info'
                  : 'text-primary hover:bg-card'
              }`}
              role="option"
              aria-selected={option.value === value}
            >
              {option.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}