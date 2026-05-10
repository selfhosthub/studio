// ui/features/marketplace/components/VersionSelectModal.tsx

'use client';

import React, { useState } from 'react';
import { X, Download, Calendar, FileText } from 'lucide-react';
import { PackageVersion, MarketplacePackage } from '@/entities/provider';
import { Modal } from '@/shared/ui';

interface VersionSelectModalProps {
  package: MarketplacePackage;
  onClose: () => void;
  onInstall: (version: PackageVersion) => void;
  isInstalling: boolean;
}

export default function VersionSelectModal({
  package: pkg,
  onClose,
  onInstall,
  isInstalling,
}: VersionSelectModalProps) {
  // Get versions - if versions array exists, use it; otherwise create from download_url
  const versions: PackageVersion[] = pkg.versions?.length
    ? pkg.versions
    : pkg.download_url
    ? [{ version: pkg.version || '1.0.0', download_url: pkg.download_url }]
    : [];

  // Default to first (latest) version
  const [selectedVersion, setSelectedVersion] = useState<PackageVersion | null>(
    versions[0] || null
  );

  const handleInstall = () => {
    if (selectedVersion) {
      onInstall(selectedVersion);
    }
  };

  // Format date for display
  const formatDate = (dateStr?: string) => {
    if (!dateStr) return null;
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} size="md">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-primary px-6 py-4">
        <div>
          <h3 className="text-lg font-semibold text-primary">
            Install {pkg.display_name}
          </h3>
          <p className="mt-1 text-sm text-secondary">
            Select a version to install
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-muted hover:text-secondary"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Version List */}
      <div className="px-6 py-4 max-h-80 overflow-y-auto">
        {versions.length === 0 ? (
          <p className="text-center text-secondary py-4">
            No versions available for download.
          </p>
        ) : (
          <div className="space-y-2">
            {versions.map((ver, idx) => (
              <label
                key={ver.version}
                className={`flex items-start p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedVersion?.version === ver.version
                    ? 'border-info bg-info-subtle'
                    : 'border-primary hover:bg-surface /50'
                }`}
              >
                <input
                  type="radio"
                  name="version"
                  value={ver.version}
                  checked={selectedVersion?.version === ver.version}
                  onChange={() => setSelectedVersion(ver)}
                  className="mt-1 h-4 w-4 text-info border-primary focus:ring-blue-500"
                />
                <div className="ml-3 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-primary">
                      v{ver.version}
                    </span>
                    {idx === 0 && (
                      <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-success-subtle text-success">
                        Latest
                      </span>
                    )}
                    {pkg.installed_version === ver.version && (
                      <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-info-subtle text-info">
                        Installed
                      </span>
                    )}
                  </div>
                  {ver.release_date && (
                    <div className="flex items-center mt-1 text-xs text-secondary">
                      <Calendar className="h-3 w-3 mr-1" />
                      {formatDate(ver.release_date)}
                    </div>
                  )}
                  {ver.changelog && (
                    <div className="mt-2 text-sm text-secondary">
                      <div className="flex items-start">
                        <FileText className="h-3 w-3 mr-1 mt-0.5 flex-shrink-0" />
                        <span>{ver.changelog}</span>
                      </div>
                    </div>
                  )}
                </div>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end gap-3 border-t border-primary px-6 py-4">
        <button
          onClick={onClose}
          disabled={isInstalling}
          className="px-4 py-2 text-sm font-medium text-secondary bg-card border border-primary rounded-md hover:bg-surface disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={handleInstall}
          disabled={!selectedVersion || isInstalling}
          className="btn-primary inline-flex items-center text-sm"
        >
          {isInstalling ? (
            <>
              <span className="animate-spin mr-2">...</span>
              Installing...
            </>
          ) : (
            <>
              <Download className="h-4 w-4 mr-2" />
              Install v{selectedVersion?.version}
            </>
          )}
        </button>
      </div>
    </Modal>
  );
}
