// ui/app/(authenticated)/comfyui/marketplace/components/ComfyUIMarketplaceTab.tsx

'use client';

import React, { useState } from 'react';
import {
  ResourceTable,
  SearchInput,
  EmptyState,
  Modal,
  type ResourceColumnConfig,
} from '@/shared/ui';
import {
  getComfyUIWorkflowDetail,
  type MarketplaceComfyUI,
  type MarketplaceComfyUIDetail,
} from '@/shared/api';
import { InstallAllDropdown } from '@/features/marketplace';
import {
  Download,
  Trash2,
  RefreshCw,
} from 'lucide-react';
import { useComfyUIMarketplace } from './useComfyUIMarketplace';
import { formatStatus } from '@/shared/lib/format-utils';

export function ComfyUIMarketplaceTab() {
  const mp = useComfyUIMarketplace();
  const [viewWorkflow, setViewWorkflow] = useState<MarketplaceComfyUI | null>(null);
  const [detail, setDetail] = useState<MarketplaceComfyUIDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Catalog list omits the workflow package JSON to stay lean; fetch the full
  // detail (graph + installed flag) on modal-open.
  const openWorkflow = async (tpl: MarketplaceComfyUI) => {
    setViewWorkflow(tpl);
    setDetail(null);
    setDetailLoading(true);
    try {
      const fetched = await getComfyUIWorkflowDetail(tpl.id);
      setDetail(fetched);
    } catch {
      // Leave the metadata-only view in place on failure.
    } finally {
      setDetailLoading(false);
    }
  };

  const closeWorkflow = () => {
    setViewWorkflow(null);
    setDetail(null);
  };

  const titleCase = (s: string) =>
    s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  const getTierBadge = (tier: string) => tier === 'plus'
    ? { label: 'Plus', className: 'bg-warning-subtle text-warning' }
    : { label: 'Community', className: 'bg-surface text-secondary' };

  // Guard against a stale fetch landing after another row was opened.
  const activeDetail = detail && detail.id === viewWorkflow?.id ? detail : null;

  // Graph summary for the detail modal: node count + distinct node class types.
  const graphNodes = activeDetail?.workflow?.graph ? Object.values(activeDetail.workflow.graph) : [];
  const classTypes = Array.from(
    new Set(graphNodes.map((n) => n.class_type).filter((c): c is string => !!c)),
  ).sort();

  const columns: ResourceColumnConfig<MarketplaceComfyUI>[] = [
    {
      key: 'display_name',
      header: 'Workflow',
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
          {!tpl.requirements_met && tpl.missing_packages.length > 0 && (
            <div className="text-xs text-warning mt-1">
              Requires: {tpl.missing_packages.join(', ')}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      cellClassName: 'wrap-anywhere',
      align: 'center',
      sortValue: (tpl) => titleCase(tpl.category),
      render: (tpl) => (
        <span className="text-sm">
          {titleCase(tpl.category)}
        </span>
      ),
    },
    {
      key: 'tier',
      header: 'Tier',
      align: 'center',
      sortValue: (tpl) => getTierBadge(tpl.tier).label,
      render: (tpl) => (
        <span className={`badge ${getTierBadge(tpl.tier).className}`}>
          {getTierBadge(tpl.tier).label}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      align: 'center',
      sortValue: (tpl) => tpl.status,
      render: (tpl) => tpl.status ? (
        <span className="badge bg-info-subtle text-info">
          {formatStatus(tpl.status)}
        </span>
      ) : (
        <span className="text-muted text-sm">-</span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (tpl) => (
        <div className="flex justify-center gap-2 items-center max-md:flex-col max-md:items-stretch" onClick={(e) => e.stopPropagation()}>
          {mp.installedIds.has(tpl.id) ? (
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
            <button
              type="button"
              onClick={() => mp.handleInstall(tpl)}
              disabled={mp.installingId === tpl.id}
              className="action-btn-install"
            >
              {mp.installingId === tpl.id ? (
                'Installing...'
              ) : (
                <>
                  <Download className="w-3 h-3 mr-1" />
                  Install
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
        prefPage="comfyui-marketplace"
        pagination={{ itemLabel: 'workflow' }}
        pageResetKey={`${mp.search}|${mp.categoryFilter}|${mp.tierFilter}`}
        loading={mp.loading}
        loadingMessage="Loading marketplace catalog..."
        error={mp.error}
        onRetry={mp.fetchMarketplace}
        onRowClick={openWorkflow}
        emptyState={
          <EmptyState
            title="No Workflows Found"
            description={
              mp.search
                ? `No results for "${mp.search}".`
                : mp.tierFilter !== 'all' || mp.categoryFilter !== 'all'
                ? 'Try adjusting your filters to see more workflows.'
                : 'No ComfyUI workflows are available yet.'
            }
            action={mp.search ? (
              <button type="button" className="btn-secondary" onClick={() => mp.setSearch('')}>
                Clear search
              </button>
            ) : undefined}
          />
        }
        toolbar={
          <>
            <div className="w-full sm:w-auto sm:flex-1">
              <SearchInput
                value={mp.search}
                onChange={mp.setSearch}
                placeholder="Search marketplace..."
              />
            </div>
            {(mp.catalogWorkflows.some(t => t.tier === 'community' && !mp.installedIds.has(t.id)) ||
              mp.catalogWorkflows.some(t => t.tier === 'plus' && !mp.installedIds.has(t.id))) && (
              <InstallAllDropdown
                hasCommunity={mp.catalogWorkflows.some(t => t.tier === 'community' && !mp.installedIds.has(t.id))}
                hasPlus={mp.catalogWorkflows.some(t => t.tier === 'plus' && !mp.installedIds.has(t.id))}
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
            <select
              value={mp.categoryFilter}
              onChange={(e) => mp.setCategoryFilter(e.target.value)}
              className="form-select text-sm w-auto"
            >
              <option value="all">All Categories</option>
              {mp.catalogFilterOptions.category.map((cat) => (
                <option key={cat} value={cat}>
                  {titleCase(cat)}
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
      />
      {/* Read-only workflow detail modal */}
      <Modal
        isOpen={!!viewWorkflow}
        onClose={closeWorkflow}
        title={viewWorkflow?.display_name ?? 'Workflow Details'} // defaults-ok
        size="lg"
      >
        {viewWorkflow && (
          <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto">
            {/* Meta info */}
            <div className="flex flex-wrap gap-3 text-sm">
              <span className="badge bg-surface text-secondary">
                {titleCase(viewWorkflow.category)}
              </span>
              <span className={`badge ${getTierBadge(viewWorkflow.tier).className}`}>
                {getTierBadge(viewWorkflow.tier).label}
              </span>
              {viewWorkflow.status && (
                <span className="badge bg-info-subtle text-info">
                  {formatStatus(viewWorkflow.status)}
                </span>
              )}
              {(activeDetail?.installed ?? mp.installedIds.has(viewWorkflow.id)) && (
                <span className="badge bg-success-subtle text-success">
                  Installed
                </span>
              )}
              {viewWorkflow.version && (
                <span className="text-muted">v{viewWorkflow.version}</span>
              )}
              {viewWorkflow.author && (
                <span className="text-muted">by {viewWorkflow.author}</span>
              )}
            </div>

            {/* Description */}
            {viewWorkflow.description && (
              <div>
                <h4 className="text-sm font-semibold text-primary mb-1">Description</h4>
                <p className="text-sm text-secondary">{viewWorkflow.description}</p>
              </div>
            )}

            {/* Required packages */}
            {viewWorkflow.requires.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-primary mb-2">Required Packages</h4>
                <div className="space-y-2">
                  {viewWorkflow.requires.map((pkg) => {
                    const missing = viewWorkflow.missing_packages.includes(pkg);
                    return (
                      <div key={pkg} className="bg-surface rounded-md p-3 text-sm">
                        <span className="font-medium text-primary">{pkg}</span>
                        <span className={`badge ml-2 ${missing ? 'bg-warning-subtle text-warning' : 'bg-success-subtle text-success'}`}>
                          {missing ? 'Not installed' : 'Installed'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Loading full detail (workflow package fetched on open) */}
            {detailLoading && <p className="text-sm text-muted">Loading workflow details...</p>}

            {/* Graph summary */}
            {activeDetail?.workflow?.graph && (
              <div>
                <h4 className="text-sm font-semibold text-primary mb-2">
                  Graph ({graphNodes.length} node{graphNodes.length !== 1 ? 's' : ''})
                </h4>
                {classTypes.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {classTypes.map((ct) => (
                      <span key={ct} className="badge bg-surface text-secondary">
                        {ct}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Close button */}
            <div className="flex justify-end pt-2 border-t border-primary">
              <button
                type="button"
                onClick={closeWorkflow}
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
