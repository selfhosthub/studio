// ui/app/ai-agents/prompts/list/components/PromptsMarketplaceTab.tsx

'use client';

import React, { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHeader,
  TableHeaderCell,
  TableRow,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
  Modal,
} from '@/shared/ui';
import type { MarketplacePrompt } from '@/shared/api';
import { InstallAllDropdown } from '@/features/marketplace';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import {
  Download,
  Trash2,
  RefreshCw,
  Lock,
  ChevronUp,
  ChevronDown,
} from 'lucide-react';
import { usePromptsMarketplace } from './usePromptsMarketplace';
import type { SortField } from './usePromptsMarketplace';

interface PromptsMarketplaceTabProps {
  isSuperAdmin: boolean;
  onPromptsChanged: () => void;
}

export function PromptsMarketplaceTab({ isSuperAdmin, onPromptsChanged }: PromptsMarketplaceTabProps) {
  const mp = usePromptsMarketplace({ isSuperAdmin, onPromptsChanged });
  const [viewPrompt, setViewPrompt] = useState<MarketplacePrompt | null>(null);

  const sortIcon = (field: SortField) => {
    if (mp.sortField !== field) return null;
    return mp.sortDirection === 'asc'
      ? <ChevronUp className="inline w-4 h-4 ml-1" />
      : <ChevronDown className="inline w-4 h-4 ml-1" />;
  };

  const getTierBadge = (tier: string) => tier === 'advanced'
    ? { label: 'Advanced', className: 'bg-warning-subtle text-warning' }
    : { label: 'Basic', className: 'bg-surface text-secondary' };

  return (
    <>
      {/* Search + Filters + Admin Actions + Pagination */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="w-full sm:w-auto sm:flex-1">
          <SearchInput
            value={mp.search}
            onChange={mp.setSearch}
            placeholder="Search marketplace..."
          />
        </div>
        <select
          value={mp.categoryFilter}
          onChange={(e) => mp.setCategoryFilter(e.target.value)}
          className="form-select text-sm w-auto"
        >
          <option value="all">All Categories</option>
          {mp.catalogFilterOptions.category.map((cat) => (
            <option key={cat} value={cat}>
              {cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
            </option>
          ))}
        </select>
        <select
          value={mp.tierFilter}
          onChange={(e) => mp.setTierFilter(e.target.value as 'all' | 'basic' | 'advanced')}
          className="form-select text-sm w-auto"
        >
          <option value="all">All Tiers</option>
          <option value="basic">Basic</option>
          <option value="advanced">Advanced</option>
        </select>
        {isSuperAdmin && (
          <>
            {(mp.catalogPrompts.some(t => t.tier === 'basic' && !mp.installedIds.has(t.id)) ||
              (mp.tokenConfigured && mp.catalogPrompts.some(t => t.tier === 'advanced' && !mp.installedIds.has(t.id)))) && (
              <InstallAllDropdown
                hasBasic={mp.catalogPrompts.some(t => t.tier === 'basic' && !mp.installedIds.has(t.id))}
                hasAdvanced={mp.tokenConfigured && mp.catalogPrompts.some(t => t.tier === 'advanced' && !mp.installedIds.has(t.id))}
                installing={mp.installAllInProgress}
                onInstall={mp.handleInstallAllByTier}
              />
            )}
            <button
              onClick={mp.handleRefresh}
              disabled={mp.uploading}
              className="btn-primary inline-flex items-center justify-center gap-2"
            >
              <RefreshCw className={`w-4 h-4${mp.uploading ? ' animate-spin' : ''}`} />
              {mp.uploading ? 'Refreshing...' : 'Refresh Catalog'}
            </button>
          </>
        )}
        <Pagination
          currentPage={mp.page}
          totalPages={mp.totalPages}
          totalCount={mp.filteredCatalog.length}
          pageSize={mp.pageSize}
          onPageChange={mp.setPage}
          onPageSizeChange={(size) => {
            mp.setPageSize(size);
            mp.setPage(1);
          }}
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          position="top"
          itemLabel="prompts"
        />
      </div>

      {mp.loading && <LoadingState message="Loading marketplace catalog..." />}

      {!mp.loading && mp.error && (
        <ErrorState title="Error" message={mp.error} onRetry={mp.fetchMarketplace} />
      )}

      {!mp.loading && !mp.error && mp.filteredCatalog.length === 0 && (
        <EmptyState
          title="No Prompts Found"
          description={
            mp.search || mp.tierFilter !== 'all' || mp.categoryFilter !== 'all'
              ? 'Try adjusting your filters to see more prompts.'
              : 'No prompts are available yet.'
          }
        />
      )}

      {!mp.loading && !mp.error && mp.paginatedCatalog.length > 0 && (
        <>
          <TableContainer>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell onClick={() => mp.handleSort('display_name')}>
                    Prompt
                    {sortIcon('display_name')}
                  </TableHeaderCell>
                  <TableHeaderCell align="center" onClick={() => mp.handleSort('category')}>
                    Category
                    {sortIcon('category')}
                  </TableHeaderCell>
                  <TableHeaderCell align="center" onClick={() => mp.handleSort('tier')}>
                    Tier
                    {sortIcon('tier')}
                  </TableHeaderCell>
                  <TableHeaderCell align="center">Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mp.paginatedCatalog.map((tpl) => (
                  <TableRow key={tpl.id} onClick={() => setViewPrompt(tpl)}>
                    <TableCell>
                      <div>
                        <div className="text-sm font-medium">
                          {tpl.display_name}
                          {tpl.version && (
                            <span className="ml-2 text-xs text-muted">
                              v{tpl.version}
                            </span>
                          )}
                        </div>
                        <div className="section-subtitle line-clamp-2">
                          {tpl.description}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell align="center">
                      <span className="text-sm">
                        {tpl.category
                          .replace(/_/g, ' ')
                          .replace(/\b\w/g, (c) => c.toUpperCase())}
                      </span>
                    </TableCell>
                    <TableCell align="center">
                      <span className={`badge${getTierBadge(tpl.tier).className}`}>
                        {getTierBadge(tpl.tier).label}
                      </span>
                    </TableCell>
                    <TableCell align="center">
                      <div className="flex justify-center gap-2" onClick={(e) => e.stopPropagation()}>
                        {mp.installedIds.has(tpl.id) ? (
                          isSuperAdmin ? (
                            <button
                              type="button"
                              onClick={() => mp.handleUninstall(tpl.id)}
                              disabled={mp.uninstallingId === tpl.id}
                              className="action-btn-uninstall"
                            >
                              {mp.uninstallingId === tpl.id ? (
                                'Removing...'
                              ) : (
                                <>
                                  <Trash2 className="w-3 h-3 mr-1" />
                                  Remove
                                </>
                              )}
                            </button>
                          ) : (
                            <span className="text-xs text-success font-medium">
                              Copied
                            </span>
                          )
                        ) : tpl.tier === 'advanced' && !mp.tokenConfigured ? (
                          <span
                            className="action-btn-locked"
                            title="Advanced prompt - requires entitlement token"
                          >
                            <Lock className="w-3 h-3 mr-1" />
                            Advanced
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => mp.handleInstall(tpl)}
                            disabled={mp.installingId === tpl.id}
                            className="action-btn-install"
                          >
                            {mp.installingId === tpl.id ? (
                              isSuperAdmin ? 'Installing...' : 'Copying...'
                            ) : (
                              <>
                                <Download className="w-3 h-3 mr-1" />
                                {isSuperAdmin ? 'Install' : 'Copy'}
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Pagination
            currentPage={mp.page}
            totalPages={mp.totalPages}
            totalCount={mp.filteredCatalog.length}
            pageSize={mp.pageSize}
            onPageChange={mp.setPage}
            itemLabel="prompts"
            position="bottom"
          />
        </>
      )}
      {/* Read-only prompt detail modal */}
      <Modal
        isOpen={!!viewPrompt}
        onClose={() => setViewPrompt(null)}
        title={viewPrompt?.display_name ?? 'Prompt Details'}
        size="lg"
      >
        {viewPrompt && (
          <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto">
            {/* Meta info */}
            <div className="flex flex-wrap gap-3 text-sm">
              <span className="badge bg-surface text-secondary">
                {viewPrompt.category.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
              </span>
              <span className={`badge ${getTierBadge(viewPrompt.tier).className}`}>
                {getTierBadge(viewPrompt.tier).label}
              </span>
              {viewPrompt.version && (
                <span className="text-muted">v{viewPrompt.version}</span>
              )}
              {viewPrompt.author && (
                <span className="text-muted">by {viewPrompt.author}</span>
              )}
            </div>

            {/* Description */}
            {viewPrompt.description && (
              <div>
                <h4 className="text-sm font-semibold text-primary mb-1">Description</h4>
                <p className="text-sm text-secondary">{viewPrompt.description}</p>
              </div>
            )}

            {/* Prompt chunks */}
            {viewPrompt.chunks.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-primary mb-2">Prompt</h4>
                <div className="space-y-2">
                  {viewPrompt.chunks
                    .sort((a, b) => a.order - b.order)
                    .map((chunk, idx) => (
                      <div key={idx} className="bg-surface rounded-md p-3">
                        {chunk.role && (
                          <span className="text-xs font-medium text-muted uppercase tracking-wide">
                            {chunk.role}
                          </span>
                        )}
                        <pre className="text-sm text-secondary whitespace-pre-wrap font-mono mt-1">
                          {chunk.text}
                        </pre>
                        {chunk.variable && (
                          <span className="text-xs text-info mt-1 inline-block">
                            Variable: {chunk.variable}
                          </span>
                        )}
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Variables */}
            {viewPrompt.variables.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-primary mb-2">Variables</h4>
                <div className="space-y-2">
                  {viewPrompt.variables.map((v, idx) => (
                    <div key={idx} className="bg-surface rounded-md p-3 text-sm">
                      <span className="font-medium text-primary">{v.label || v.name}</span>
                      <span className="text-muted ml-2">({v.type})</span>
                      {v.default && (
                        <span className="text-secondary ml-2">Default: {v.default}</span>
                      )}
                      {v.options && v.options.length > 0 && (
                        <div className="text-muted mt-1">
                          Options: {v.options.join(', ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Close button */}
            <div className="flex justify-end pt-2 border-t border-primary">
              <button
                type="button"
                onClick={() => setViewPrompt(null)}
                className="btn-secondary text-sm"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
