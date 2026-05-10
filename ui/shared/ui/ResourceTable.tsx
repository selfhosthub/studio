// ui/shared/ui/ResourceTable.tsx

'use client';

import React, { useState, useMemo, useEffect, ReactNode } from 'react';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  TableHeaderCell,
  TableContainer,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
  ActionButton,
} from './Table';
import { getStoredPageSize, PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import { ChevronUp, ChevronDown } from 'lucide-react';

export interface ColumnConfig<T> {
  key: string;
  header: string;
  align?: 'left' | 'center' | 'right';
  sortable?: boolean;
  sortKey?: string;
  render: (item: T) => ReactNode;
  visible?: boolean;
}

export interface SearchConfig<T> {
  placeholder?: string;
  matchFn: (item: T, query: string) => boolean;
}

export interface FilterConfig<T> {
  key: string;
  label: string;
  options: { value: string; label: string }[];
  matchFn: (item: T, value: string) => boolean;
}

export interface SortConfig<T> {
  defaultField: string;
  defaultDirection?: 'asc' | 'desc';
  compareFn: (a: T, b: T, field: string) => number;
}

export interface PaginationConfig {
  storageKey: string;
  defaultSize?: number;
  options?: number[];
  itemLabel?: string;
}

export interface ActionConfig<T> {
  label: string | ((item: T) => string);
  variant: 'active' | 'change' | 'destructive' | 'warning' | 'navigate' | 'secondary';
  onClick: (item: T) => void;
  visible?: (item: T) => boolean;
  disabled?: (item: T) => boolean;
}

export interface EmptyConfig {
  title: string;
  description?: string | ((hasFilters: boolean) => string);
  icon?: ReactNode;
  action?: ReactNode;
}

export interface ResourceTableProps<T> {
  data: T[];
  loading: boolean;
  error?: string | null;
  onRetry?: () => void;
  getItemId: (item: T) => string;

  columns: ColumnConfig<T>[];
  search?: SearchConfig<T>;
  filters?: FilterConfig<T>[];
  sort?: SortConfig<T>;
  pagination?: PaginationConfig;
  actions?: ActionConfig<T>[];

  emptyState?: EmptyConfig;
  loadingMessage?: string;
  errorTitle?: string;
  headerContent?: ReactNode;
  className?: string;
}

export function ResourceTable<T>({
  data,
  loading,
  error,
  onRetry,
  getItemId,
  columns,
  search,
  filters,
  sort,
  pagination,
  actions,
  emptyState,
  loadingMessage = 'Loading...',
  errorTitle = 'Error',
  headerContent,
  className = '',
}: ResourceTableProps<T>) {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterValues, setFilterValues] = useState<Record<string, string>>(() => {
    const defaults: Record<string, string> = {};
    filters?.forEach((f) => { defaults[f.key] = 'all'; });
    return defaults;
  });
  const [sortField, setSortField] = useState(sort?.defaultField ?? '');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>(sort?.defaultDirection ?? 'asc');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(() =>
    pagination ? getStoredPageSize(pagination.storageKey, pagination.defaultSize ?? 20) : 20
  );

  const filterKeys = filters?.map(f => f.key).join(',');
  useEffect(() => {
    if (filters) {
      const defaults: Record<string, string> = {};
      filters.forEach((f) => { defaults[f.key] = 'all'; });
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFilterValues(defaults);
    }
  }, [filterKeys, filters]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurrentPage(1);
  }, [searchTerm, filterValues]);

  const paginationStorageKey = pagination?.storageKey;
  useEffect(() => {
    if (paginationStorageKey) {
      localStorage.setItem(paginationStorageKey, String(pageSize));
    }
  }, [pageSize, paginationStorageKey]);

  const visibleColumns = useMemo(
    () => columns.filter((c) => c.visible !== false),
    [columns]
  );

  const filtered = useMemo(() => {
    let result = data;

    if (search && searchTerm) {
      const q = searchTerm.toLowerCase();
      result = result.filter((item) => search.matchFn(item, q));
    }

    if (filters) {
      for (const f of filters) {
        const val = filterValues[f.key];
        if (val && val !== 'all') {
          result = result.filter((item) => f.matchFn(item, val));
        }
      }
    }

    return result;
  }, [data, searchTerm, filterValues, search, filters]);

  const sorted = useMemo(() => {
    if (!sort || !sortField) return filtered;

    const result = [...filtered];
    result.sort((a, b) => {
      const cmp = sort.compareFn(a, b, sortField);
      return sortDirection === 'asc' ? cmp : -cmp;
    });
    return result;
  }, [filtered, sort, sortField, sortDirection]);

  const totalCount = sorted.length;
  const totalPages = pagination ? Math.ceil(totalCount / pageSize) || 1 : 1;

  useEffect(() => {
    if (currentPage > totalPages) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCurrentPage(1);
    }
  }, [totalPages, currentPage]);

  const paginated = useMemo(() => {
    if (!pagination) return sorted;
    return sorted.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  }, [sorted, pagination, currentPage, pageSize]);

  const handleSort = (key: string) => {
    if (sortField === key) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(key);
      setSortDirection('asc');
    }
  };

  const hasActiveFilters = searchTerm !== '' || Object.values(filterValues).some((v) => v !== 'all');

  if (loading) {
    return <LoadingState message={loadingMessage} />;
  }

  if (error) {
    return (
      <ErrorState
        title={errorTitle}
        message={error}
        onRetry={onRetry}
        retryLabel="Refresh Page"
      />
    );
  }

  const pageSizeOptions = pagination?.options ?? PAGE_SIZE_OPTIONS;
  const itemLabel = pagination?.itemLabel ?? 'item';

  return (
    <div className={className}>
      {(search || (filters && filters.length > 0)) && (
        <div className="mb-6 flex flex-col sm:flex-row gap-3">
          {search && (
            <div className="flex-1">
              <SearchInput
                value={searchTerm}
                onChange={setSearchTerm}
                placeholder={search.placeholder}
              />
            </div>
          )}
          {filters?.map((f) => (
            <select
              key={f.key}
              value={filterValues[f.key]}
              onChange={(e) =>
                setFilterValues((prev) => ({ ...prev, [f.key]: e.target.value }))
              }
              className="form-select text-sm"
            >
              <option value="all">All {f.label}</option>
              {f.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          ))}
        </div>
      )}

      {headerContent}

      {totalCount === 0 && emptyState && (
        <EmptyState
          icon={emptyState.icon}
          title={emptyState.title}
          description={
            typeof emptyState.description === 'function'
              ? emptyState.description(hasActiveFilters)
              : emptyState.description
          }
          action={emptyState.action}
        />
      )}

      {totalCount > 0 && (
        <>
          {pagination && (
            <div className="flex items-center justify-between mb-4">
              <div className="text-sm text-secondary">
                {totalCount} {itemLabel}{totalCount === 1 ? '' : 's'}
              </div>
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                totalCount={totalCount}
                pageSize={pageSize}
                onPageChange={setCurrentPage}
                onPageSizeChange={(size) => {
                  setPageSize(size);
                  setCurrentPage(1);
                }}
                pageSizeOptions={pageSizeOptions}
                position="top"
                itemLabel={itemLabel}
              />
            </div>
          )}

          <TableContainer>
            <Table>
              <TableHeader>
                <TableRow>
                  {visibleColumns.map((col) => {
                    const isSortable = sort && col.sortable;
                    const sortKey = col.sortKey ?? col.key;
                    const isActive = sortField === sortKey;

                    if (isSortable) {
                      return (
                        <th
                          key={col.key}
                          scope="col"
                          className={`table-header-cell ${
                            col.align === 'center' ? 'text-center' : col.align === 'right' ? 'text-right' : 'text-left'
                          } cursor-pointer hover:bg-input`}
                          onClick={() => handleSort(sortKey)}
                        >
                          {col.header}
                          {isActive && (
                            sortDirection === 'asc'
                              ? <ChevronUp className="inline w-4 h-4 ml-1" />
                              : <ChevronDown className="inline w-4 h-4 ml-1" />
                          )}
                        </th>
                      );
                    }

                    return (
                      <TableHeaderCell key={col.key} align={col.align}>
                        {col.header}
                      </TableHeaderCell>
                    );
                  })}
                  {actions && actions.length > 0 && (
                    <TableHeaderCell align="center">Actions</TableHeaderCell>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginated.map((item) => (
                  <TableRow key={getItemId(item)}>
                    {visibleColumns.map((col) => (
                      <TableCell key={col.key} align={col.align}>
                        {col.render(item)}
                      </TableCell>
                    ))}
                    {actions && actions.length > 0 && (
                      <TableCell align="center">
                        <div className="flex justify-center space-x-2">
                          {actions
                            .filter((a) => !a.visible || a.visible(item))
                            .map((a, i) => (
                              <ActionButton
                                key={i}
                                variant={a.variant}
                                onClick={() => a.onClick(item)}
                                disabled={a.disabled ? a.disabled(item) : false}
                              >
                                {typeof a.label === 'function' ? a.label(item) : a.label}
                              </ActionButton>
                            ))}
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {pagination && (
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalCount={totalCount}
              pageSize={pageSize}
              onPageChange={setCurrentPage}
              itemLabel={itemLabel}
              position="bottom"
            />
          )}
        </>
      )}
    </div>
  );
}
