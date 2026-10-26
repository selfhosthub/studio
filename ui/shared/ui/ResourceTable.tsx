// ui/shared/ui/ResourceTable.tsx

'use client';

import React, { useId, useState, ReactNode } from 'react';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  TableHeaderCell,
  TableContainer,
  Pagination,
  LoadingState,
  ErrorState,
} from './Table';
import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import { useListPref, isPageSize, isString, oneOf } from '@/shared/hooks/useListPref';
import type { ListPrefPage } from '@/shared/lib/constants';
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';

export type SortDirection = 'asc' | 'desc';

export type SortValue = string | number | boolean | Date | null | undefined;

/** Primary columns render at every width; secondary columns move into the row detail below md. */
export type ColumnPriority = 'primary' | 'secondary';

export interface ColumnConfig<T> {
  key: string;
  header: ReactNode;
  align?: 'left' | 'center' | 'right';
  /** Value the column sorts by; a column without one is not sortable. */
  sortValue?: (item: T) => SortValue;
  render: (item: T) => ReactNode;
  /** Defaults to primary for the name and actions columns and secondary for every other column. */
  priority?: ColumnPriority;
  visible?: boolean;
  headerClassName?: string;
  cellClassName?: string | ((item: T) => string);
}

export interface SortState {
  field: string | null;
  direction: SortDirection;
}

export interface ControlledSort extends SortState {
  onChange: (next: SortState) => void;
  /** True when the server returns rows already sorted by the field. */
  server?: boolean;
}

export interface ServerPagination {
  currentPage: number;
  totalCount: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}

export interface PaginationConfig {
  itemLabel?: string;
  /** Pages the server already sliced; the table renders the pager only. */
  server?: ServerPagination;
}

export interface ResourceTableProps<T> {
  data: T[];
  getItemId: (item: T) => string;
  columns: ColumnConfig<T>[];
  /** Key of the column holding the row's label; defaults to the first visible column. */
  nameColumn?: string;

  /** Persists sort and page size under shs:list:<prefPage>:<field>. */
  prefPage?: ListPrefPage;
  pagination?: boolean | PaginationConfig;
  /** The table returns to page 1 when this value changes. */
  pageResetKey?: string;
  sort?: ControlledSort;
  /** Column key or accessor that orders rows with equal sort values, ascending; defaults to the name or display_name column. */
  tieBreaker?: string | ((item: T) => SortValue);

  toolbar?: ReactNode;
  loading?: boolean;
  loadingMessage?: string;
  error?: string | null;
  errorTitle?: string;
  onRetry?: () => void;
  /** Rendered in place of the table when there are no rows. */
  emptyState?: ReactNode;
  /** Rendered as a single row inside the table when there are no rows. */
  emptyMessage?: ReactNode;

  onRowClick?: (item: T) => void;
  rowClassName?: (item: T) => string;
  ariaLabel?: string;
  className?: string;
  containerClassName?: string;
}

const SORT_DIRECTIONS = ['asc', 'desc'] as const;
const ALIGN_CLASS = { left: 'text-left', center: 'text-center', right: 'text-right' } as const;

/** Pins the first column while the rest of the table scrolls sideways below the md breakpoint. */
export const PINNED_COLUMN_CLASS =
  'max-md:sticky max-md:-left-px max-md:z-[1] max-md:shadow-[inset_-1px_0_0_var(--theme-border-primary)]';

/** Narrows cell padding below the md breakpoint. */
const COMPACT_CELL_CLASS = 'max-md:px-2!';

/** Hides a secondary column below the md breakpoint. */
const SECONDARY_COLUMN_CLASS = 'max-md:hidden';

/** Wraps the name cell at spaces, hyphens and slashes, breaking a single overlong word only when it cannot fit. */
const NAME_CELL_CLASS = 'whitespace-normal wrap-anywhere';

const ACTIONS_KEY = 'actions';

/** Key of the name column: the given key when it names a column, otherwise the first column. */
export function nameColumnKey<T>(columns: ColumnConfig<T>[], nameColumn?: string): string | undefined {
  return columns.find((c) => c.key === nameColumn)?.key ?? columns[0]?.key;
}

/** A column's priority: an explicit priority wins, otherwise the name and actions columns are primary. */
export function columnPriority<T>(column: ColumnConfig<T>, nameKey: string | undefined): ColumnPriority {
  if (column.priority) return column.priority;
  return column.key === nameKey || column.key === ACTIONS_KEY ? 'primary' : 'secondary';
}

/** Columns that move into the row detail below md. */
export function secondaryColumns<T>(columns: ColumnConfig<T>[], nameColumn?: string): ColumnConfig<T>[] {
  const nameKey = nameColumnKey(columns, nameColumn);
  return columns.filter((c) => columnPriority(c, nameKey) === 'secondary');
}

const collator = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true });

function normalize(value: SortValue): string | number | null {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) return value.getTime();
  if (typeof value === 'boolean') return value ? 1 : 0;
  return value;
}

/** Compares two sort values; empty values order after every other value. */
export function compareSortValues(a: SortValue, b: SortValue): number {
  const x = normalize(a);
  const y = normalize(b);
  if (x === null && y === null) return 0;
  if (x === null) return 1;
  if (y === null) return -1;
  if (typeof x === 'number' && typeof y === 'number') return x - y;
  return collator.compare(String(x), String(y));
}

/** Sorts rows by a column, then by the tie-breaker ascending, then by id; empty values go last. */
export function sortRows<T>(
  rows: T[],
  sortValue: (item: T) => SortValue,
  direction: SortDirection,
  getItemId: (item: T) => string,
  tieBreak?: (item: T) => SortValue,
): T[] {
  const sign = direction === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = sortValue(a);
    const vb = sortValue(b);
    const emptyA = normalize(va) === null;
    const emptyB = normalize(vb) === null;
    if (emptyA !== emptyB) return emptyA ? 1 : -1;
    const cmp = compareSortValues(va, vb) * sign;
    if (cmp !== 0) return cmp;
    const tie = tieBreak ? compareSortValues(tieBreak(a), tieBreak(b)) : 0;
    if (tie !== 0) return tie;
    const ia = getItemId(a);
    const ib = getItemId(b);
    return ia < ib ? -1 : ia > ib ? 1 : 0;
  });
}

/** Next sort after a header click: a new column starts ascending, the active column flips. */
export function nextSort(current: SortState, field: string): SortState {
  if (current.field !== field) return { field, direction: 'asc' };
  return { field, direction: current.direction === 'asc' ? 'desc' : 'asc' };
}

const DEFAULT_TIE_BREAK_KEYS = ['name', 'display_name'];

/** Resolves the tie-breaker accessor from a column key, an accessor, or the default name column. */
export function resolveTieBreak<T>(
  columns: ColumnConfig<T>[],
  tieBreaker?: string | ((item: T) => SortValue),
): ((item: T) => SortValue) | undefined {
  if (typeof tieBreaker === 'function') return tieBreaker;
  const keys = tieBreaker ? [tieBreaker] : DEFAULT_TIE_BREAK_KEYS;
  for (const key of keys) {
    const column = columns.find((c) => c.key === key && c.sortValue);
    if (column) return column.sortValue;
  }
  return undefined;
}

export function ResourceTable<T>({
  data,
  getItemId,
  columns,
  nameColumn,
  prefPage,
  pagination,
  pageResetKey,
  sort,
  tieBreaker,
  toolbar,
  loading = false,
  loadingMessage = 'Loading...',
  error,
  errorTitle = 'Error',
  onRetry,
  emptyState,
  emptyMessage,
  onRowClick,
  rowClassName,
  ariaLabel,
  className = '',
  containerClassName = '',
}: ResourceTableProps<T>) {
  const [storedField, setStoredField] = useListPref(prefPage, 'sortField', '', isString);
  const [storedDirection, setStoredDirection] = useListPref<SortDirection>(
    prefPage, 'sortDirection', 'asc', oneOf(SORT_DIRECTIONS),
  );
  const [storedPageSize, setStoredPageSize] = useListPref(prefPage, 'pageSize', DEFAULT_PAGE_SIZE, isPageSize);
  const [page, setPage] = useState(1);
  const tableId = useId();
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());
  const [prevResetKey, setPrevResetKey] = useState(pageResetKey);
  if (pageResetKey !== prevResetKey) {
    setPrevResetKey(pageResetKey);
    setPage(1);
  }

  const visibleColumns = columns.filter((c) => c.visible !== false);
  const nameKey = nameColumnKey(visibleColumns, nameColumn);
  const detailColumns = secondaryColumns(visibleColumns, nameColumn);
  const hasDetail = detailColumns.length > 0;
  const primaryCount = visibleColumns.length - detailColumns.length;
  const isSecondary = (col: ColumnConfig<T>) => columnPriority(col, nameKey) === 'secondary';

  const [sortMenuOpen, setSortMenuOpen] = useState(false);
  const sortableColumns = visibleColumns.filter((c) => c.sortValue);
  const hasHiddenSortable = sortableColumns.some(isSecondary);

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const sortField = sort ? sort.field : storedField || null;
  const sortDirection = sort ? sort.direction : storedDirection;
  const activeColumn = visibleColumns.find((c) => c.key === sortField && c.sortValue);

  const pagerConfig = pagination ? (typeof pagination === 'object' ? pagination : {}) : null;
  const server = pagerConfig?.server;

  const handleSort = (field: string) => {
    const next = nextSort({ field: activeColumn ? activeColumn.key : null, direction: sortDirection }, field);
    if (sort) {
      sort.onChange(next);
    } else {
      setStoredField(next.field ?? '');
      setStoredDirection(next.direction);
    }
    if (!server) setPage(1);
  };

  const sorted = activeColumn?.sortValue && !sort?.server
    ? sortRows(data, activeColumn.sortValue, sortDirection, getItemId, resolveTieBreak(columns, tieBreaker))
    : data;

  const itemLabel = pagerConfig?.itemLabel;
  const pageSize = server ? server.pageSize : storedPageSize;
  const totalCount = server ? server.totalCount : sorted.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const currentPage = server ? server.currentPage : Math.min(page, totalPages);

  const rows = pagerConfig && !server
    ? sorted.slice((currentPage - 1) * pageSize, currentPage * pageSize)
    : sorted;

  const onPageChange = server ? server.onPageChange : setPage;
  const onPageSizeChange = (size: number) => {
    if (server) {
      server.onPageSizeChange(size);
    } else {
      setStoredPageSize(size);
      setPage(1);
    }
  };

  const pinClass = (index: number, extra = '') => (index === 0 ? `${PINNED_COLUMN_CLASS} ${extra}` : '');
  const hideClass = (col: ColumnConfig<T>) => (isSecondary(col) ? SECONDARY_COLUMN_CLASS : '');

  const renderHeader = (col: ColumnConfig<T>, index: number) => {
    const align = col.align ?? 'left'; // defaults-ok
    const headerClassName = `${COMPACT_CELL_CLASS} ${pinClass(index)} ${hideClass(col)} ${col.headerClassName ?? ''}`.trim();
    if (!col.sortValue) {
      return (
        <TableHeaderCell key={col.key} align={align} className={headerClassName}>
          {col.header}
        </TableHeaderCell>
      );
    }
    const isActive = activeColumn?.key === col.key;
    const ariaSort = isActive ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none';
    return (
      <th
        key={col.key}
        scope="col"
        aria-sort={ariaSort}
        className={`table-header-cell ${ALIGN_CLASS[align]} ${headerClassName}`}
      >
        <button
          type="button"
          onClick={() => handleSort(col.key)}
          className="inline-flex items-center gap-1 uppercase tracking-wider font-semibold cursor-pointer hover:underline focus-visible:underline max-md:flex-wrap max-md:tracking-normal"
        >
          {col.header}
          {isActive ? (
            sortDirection === 'asc'
              ? <ChevronUp className="w-4 h-4" aria-hidden="true" />
              : <ChevronDown className="w-4 h-4" aria-hidden="true" />
          ) : (
            <ChevronsUpDown className="w-3 h-3 opacity-40 max-md:hidden" aria-hidden="true" />
          )}
        </button>
      </th>
    );
  };

  const pagerProps = { currentPage, totalPages, totalCount, pageSize, onPageChange, itemLabel };

  let body: ReactNode;
  if (loading) {
    body = <LoadingState message={loadingMessage} />;
  } else if (error) {
    body = <ErrorState title={errorTitle} message={error} onRetry={onRetry} />;
  } else if (rows.length === 0 && emptyState) {
    body = emptyState;
  } else {
    body = (
      <>
        {hasHiddenSortable && (
          <div className="md:hidden mb-2" data-testid="resource-table-sort-menu">
            <button
              type="button"
              className="btn-secondary inline-flex items-center gap-1 text-sm px-2! py-1!"
              aria-expanded={sortMenuOpen}
              aria-controls={`${tableId}-sort-menu`}
              onClick={() => setSortMenuOpen((open) => !open)}
            >
              <ChevronsUpDown className="w-4 h-4" aria-hidden="true" />
              Sort
            </button>
            {sortMenuOpen && (
              <div id={`${tableId}-sort-menu`} role="group" aria-label="Sort by" className="flex flex-wrap gap-2 mt-2">
                {sortableColumns.map((col) => {
                  const isActive = activeColumn?.key === col.key;
                  return (
                    <button
                      key={col.key}
                      type="button"
                      aria-pressed={isActive}
                      className={`${isActive ? 'btn-primary' : 'btn-secondary'} inline-flex items-center gap-1 text-sm px-2! py-1!`}
                      onClick={() => {
                        handleSort(col.key);
                        setSortMenuOpen(false);
                      }}
                    >
                      {col.header}
                      {isActive && (sortDirection === 'asc'
                        ? <ChevronUp className="w-4 h-4" aria-hidden="true" />
                        : <ChevronDown className="w-4 h-4" aria-hidden="true" />)}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
        <TableContainer className={containerClassName}>
          <Table>
            {ariaLabel && <caption className="sr-only">{ariaLabel}</caption>}
            <TableHeader>
              <tr>
                {visibleColumns.map(renderHeader)}
                {hasDetail && (
                  <TableHeaderCell className="md:hidden w-px max-md:px-1!">
                    <span className="sr-only">Row details</span>
                  </TableHeaderCell>
                )}
              </tr>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && emptyMessage ? (
                <tr>
                  <TableCell colSpan={visibleColumns.length} align="center" className="text-muted">
                    {emptyMessage}
                  </TableCell>
                </tr>
              ) : (
                rows.map((item) => {
                  const id = getItemId(item);
                  const open = hasDetail && expanded.has(id);
                  const detailId = `${tableId}-detail-${id}`;
                  return (
                    <React.Fragment key={id}>
                      <TableRow
                        className={rowClassName ? rowClassName(item) : ''}
                        onClick={onRowClick ? () => onRowClick(item) : undefined}
                      >
                        {visibleColumns.map((col, index) => (
                          <TableCell
                            key={col.key}
                            align={col.align}
                            data-name-cell={col.key === nameKey ? '' : undefined}
                            data-actions-cell={col.key === ACTIONS_KEY ? '' : undefined}
                            className={`${COMPACT_CELL_CLASS} ${pinClass(index, 'max-md:bg-inherit')} ${col.key === nameKey ? NAME_CELL_CLASS : ''} ${hideClass(col)} ${
                              (typeof col.cellClassName === 'function' ? col.cellClassName(item) : col.cellClassName) ?? ''
                            }`.trim()}
                          >
                            {col.render(item)}
                          </TableCell>
                        ))}
                        {hasDetail && (
                          <TableCell align="center" className="md:hidden w-px max-md:px-1!">
                            <button
                              type="button"
                              aria-expanded={open}
                              aria-controls={open ? detailId : undefined}
                              aria-label="Row details"
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleExpanded(id);
                              }}
                              className="p-1 rounded-sm text-secondary hover:text-primary focus-visible:outline-2 focus-visible:outline-blue-500"
                            >
                              <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                className={`w-4 h-4 transition-transform ${open ? '' : '-rotate-90'}`}
                                aria-hidden="true"
                              >
                                <path d="m6 9 6 6 6-6" />
                              </svg>
                            </button>
                          </TableCell>
                        )}
                      </TableRow>
                      {open && (
                        <tr id={detailId} className="md:hidden" data-row-detail>
                          <TableCell colSpan={primaryCount + 1} className="max-md:px-3!">
                            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
                              {detailColumns.map((col) => (
                                <React.Fragment key={col.key}>
                                  <dt className="text-xs font-semibold uppercase tracking-wider text-secondary self-center">
                                    {col.header}
                                  </dt>
                                  <dd className="min-w-0 wrap-break-word">{col.render(item)}</dd>
                                </React.Fragment>
                              ))}
                            </dl>
                          </TableCell>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </TableBody>
          </Table>
        </TableContainer>
        {pagerConfig && totalCount > 0 && <Pagination {...pagerProps} position="bottom" />}
      </>
    );
  }

  return (
    <div className={className}>
      {(toolbar || pagerConfig) && (
        <div className="mb-6 flex flex-wrap gap-3 items-center">
          {toolbar}
          {pagerConfig && (
            <Pagination
              {...pagerProps}
              onPageSizeChange={onPageSizeChange}
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              position="top"
            />
          )}
        </div>
      )}
      {body}
    </div>
  );
}
