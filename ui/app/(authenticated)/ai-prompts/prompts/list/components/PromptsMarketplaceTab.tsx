// ui/app/(authenticated)/ai-prompts/prompts/list/components/PromptsMarketplaceTab.tsx

'use client';

import React, { useState } from 'react';
import {
  ResourceTable,
  SearchInput,
  EmptyState,
  Modal,
} from '@/shared/ui';
import type { ResourceColumnConfig } from '@/shared/ui';
import { getPromptDetail, type MarketplacePrompt } from '@/shared/api';
import { InstallAllDropdown } from '@/features/marketplace';
import {
  Download,
  Trash2,
  RefreshCw,
  Lock,
} from 'lucide-react';
import { usePromptsMarketplace } from './usePromptsMarketplace';
import { formatPromptCategory, promptCategoryOptions } from '@/shared/lib/prompt-labels';

// Tier sort order: community before plus; unknown tiers sort last.
const TIER_ORDER: Record<string, number> = { community: 0, plus: 1 };

interface PromptsMarketplaceTabProps {
  isSuperAdmin: boolean;
  onPromptsChanged: () => void;
}

export function PromptsMarketplaceTab({ isSuperAdmin, onPromptsChanged }: PromptsMarketplaceTabProps) {
  const mp = usePromptsMarketplace({ onPromptsChanged, isSuperAdmin });
  const [viewPrompt, setViewPrompt] = useState<MarketplacePrompt | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Catalog list omits chunks/variables to stay lean; fetch the full prompt
  // detail on modal-open when they're absent (super-admin pre-install view).
  const openPrompt = async (tpl: MarketplacePrompt) => {
    setViewPrompt(tpl);
    if (tpl.chunks.length > 0 || tpl.variables.length > 0) return;
    setDetailLoading(true);
    try {
      const detail = await getPromptDetail(tpl.id);
      setViewPrompt((cur) => (cur?.id === tpl.id ? detail : cur));
    } catch {
      // Leave the metadata-only view in place on failure.
    } finally {
      setDetailLoading(false);
    }
  };

  const getTierBadge = (tier: string) => tier === 'plus'
    ? { label: 'Plus', className: 'bg-warning-subtle text-warning' }
    : { label: 'Community', className: 'bg-surface text-secondary' };

  const columns: ResourceColumnConfig<MarketplacePrompt>[] = [
    {
      key: 'display_name',
      header: 'Name',
      sortValue: (tpl) => tpl.display_name,
      render: (tpl) => (
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
      ),
    },
    {
      key: 'category',
      header: 'Category',
      cellClassName: 'wrap-anywhere',
      align: 'center',
      sortValue: (tpl) => formatPromptCategory(tpl.category),
      render: (tpl) => (
        <span className="text-sm">
          {formatPromptCategory(tpl.category)}
        </span>
      ),
    },
    {
      key: 'tier',
      header: 'Tier',
      align: 'center',
      sortValue: (tpl) => TIER_ORDER[tpl.tier],
      render: (tpl) => (
        <span className={`badge${getTierBadge(tpl.tier).className}`}>
          {getTierBadge(tpl.tier).label}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (tpl) => (
        <div className="flex justify-center gap-2 items-center max-md:flex-col max-md:items-stretch" onClick={(e) => e.stopPropagation()}>
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
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => mp.handleInstall(tpl, { force: true })}
                  disabled={mp.installingId === tpl.id}
                  className="action-btn-install"
                  title="Make another copy with a unique name; lets you edit one without losing the original."
                >
                  {mp.installingId === tpl.id ? (
                    'Copying...'
                  ) : (
                    <>
                      <Download className="w-3 h-3 mr-1" />
                      Copy to Organization
                    </>
                  )}
                </button>
              </div>
            )
          ) : isSuperAdmin && tpl.tier === 'plus' && !mp.tokenConfigured ? (
            <span
              className="action-btn-locked"
              title="Plus prompt - requires entitlement token"
            >
              <Lock className="w-3 h-3 mr-1" />
              Plus
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
                  {isSuperAdmin ? 'Install' : 'Copy to Organization'}
                </>
              )}
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <ResourceTable
        data={mp.filteredCatalog}
        getItemId={(tpl) => tpl.id}
        columns={columns}
        prefPage="prompts-marketplace"
        pagination={{ itemLabel: 'prompt' }}
        pageResetKey={`${mp.search}|${mp.categoryFilter}|${mp.tierFilter}`}
        loading={mp.loading}
        loadingMessage="Loading marketplace catalog..."
        error={mp.error}
        onRetry={mp.fetchMarketplace}
        onRowClick={isSuperAdmin ? openPrompt : undefined}
        toolbar={
          <>
            <div className="w-full sm:w-auto sm:flex-1">
              <SearchInput
                value={mp.search}
                onChange={mp.setSearch}
                placeholder="Search marketplace..."
              />
            </div>
            {isSuperAdmin && (
              <>
                {(mp.catalogPrompts.some(t => t.tier === 'community' && !mp.installedIds.has(t.id)) ||
                  (mp.tokenConfigured && mp.catalogPrompts.some(t => t.tier === 'plus' && !mp.installedIds.has(t.id)))) && (
                  <InstallAllDropdown
                    hasCommunity={mp.catalogPrompts.some(t => t.tier === 'community' && !mp.installedIds.has(t.id))}
                    hasPlus={mp.tokenConfigured && mp.catalogPrompts.some(t => t.tier === 'plus' && !mp.installedIds.has(t.id))}
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
                  {mp.uploading ? 'Refreshing...' : 'Refresh'}
                </button>
              </>
            )}
            <select
              value={mp.categoryFilter}
              onChange={(e) => mp.setCategoryFilter(e.target.value)}
              className="form-select text-sm w-auto"
            >
              <option value="all">All Categories</option>
              {promptCategoryOptions(mp.catalogFilterOptions.category).map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <select
              value={mp.tierFilter}
              onChange={(e) => mp.setTierFilter(e.target.value as 'all' | 'community' | 'plus')}
              className="form-select text-sm w-auto"
            >
              <option value="all">All Tiers</option>
              <option value="community">Community</option>
              <option value="plus">Plus</option>
            </select>
          </>
        }
        emptyState={
          <EmptyState
            title="No prompts found"
            description={
              mp.search
                ? `No results for "${mp.search}".`
                : mp.tierFilter !== 'all' || mp.categoryFilter !== 'all'
                ? 'Try adjusting your filters to see more prompts.'
                : 'No prompts are available yet.'
            }
            action={mp.search ? (
              <button type="button" className="btn-secondary" onClick={() => mp.setSearch('')}>
                Clear search
              </button>
            ) : undefined}
          />
        }
      />
      {/* Read-only prompt detail modal */}
      <Modal
        isOpen={!!viewPrompt}
        onClose={() => setViewPrompt(null)}
        title={viewPrompt?.display_name ?? 'Prompt Details'} // defaults-ok
        size="lg"
      >
        {viewPrompt && (
          <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto">
            {/* Meta info */}
            <div className="flex flex-wrap gap-3 text-sm">
              <span className="badge bg-surface text-secondary">
                {formatPromptCategory(viewPrompt.category)}
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

            {/* Loading full detail (chunks/variables fetched on open) */}
            {detailLoading && viewPrompt.chunks.length === 0 && (
              <p className="text-sm text-muted">Loading prompt details...</p>
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
