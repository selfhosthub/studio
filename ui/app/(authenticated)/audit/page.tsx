// ui/app/(authenticated)/audit/page.tsx

'use client';

import { useUser } from '@/entities/user';
import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { formatDate } from '@/shared/lib/dateFormatter';
import { maskAuditMetadata } from '@/shared/lib/ip-mask';
import { getAuditEvents, AuditEvent, AuditEventFilters } from '@/shared/api';
import {
  Shield,
  AlertTriangle,
  Info,
  AlertCircle,
  User,
  Key,
  Building2,
  Workflow,
  PlayCircle,
  Plug,
  Package,
  Eye,
  ChevronDown,
  ChevronRight,
  FileText,
  ListChecks,
} from 'lucide-react';
import {
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
} from '@/shared/ui';
import { PAGE_SIZE_OPTIONS, DEFAULT_PAGE_SIZE } from '@/shared/lib/pagination';
import { useListPref, isPageSize, isString, oneOf } from '@/shared/hooks/useListPref';

const CATEGORY_FILTERS = ['all', 'security', 'configuration', 'access', 'audit'] as const;
const SEVERITY_FILTERS = ['all', 'info', 'warning', 'critical'] as const;
const RESOURCE_TYPE_FILTERS = [
  'all', 'secret', 'credential', 'user', 'organization', 'workflow', 'instance',
  'instance_step', 'file', 'provider', 'package', 'audit_log',
] as const;
const SEARCH_DEBOUNCE_MS = 300;

// Display words for resource types: singular for event text, plural for the filter
const resourceTypeLabels: Record<string, { one: string; many: string }> = {
  secret: { one: 'secret', many: 'Secrets' },
  credential: { one: 'credential', many: 'Credentials' },
  user: { one: 'user', many: 'Users' },
  organization: { one: 'organization', many: 'Organizations' },
  workflow: { one: 'workflow', many: 'Workflows' },
  instance: { one: 'instance', many: 'Instances' },
  instance_step: { one: 'instance node', many: 'Instance Nodes' },
  file: { one: 'file', many: 'Files' },
  provider: { one: 'provider', many: 'Providers' },
  package: { one: 'package', many: 'Packages' },
  audit_log: { one: 'audit log', many: 'Audit Logs' },
};

// Singular display word for a resource type, falling back to the raw value
const resourceTypeName = (type: string) => resourceTypeLabels[type]?.one ?? type.replace(/_/g, ' ');

// Resource type icons
const resourceTypeIcons: Record<string, React.ReactNode> = {
  secret: <Key size={16} />,
  credential: <Key size={16} />,
  user: <User size={16} />,
  organization: <Building2 size={16} />,
  workflow: <Workflow size={16} />,
  instance: <PlayCircle size={16} />,
  instance_step: <ListChecks size={16} />,
  file: <FileText size={16} />,
  provider: <Plug size={16} />,
  service: <Plug size={16} />,
  package: <Package size={16} />,
  audit_log: <Eye size={16} />,
};

// Severity badge styles
const severityStyles: Record<string, { bg: string; icon: React.ReactNode }> = {
  info: {
    bg: 'bg-info-subtle text-info',
    icon: <Info size={14} />
  },
  warning: {
    bg: 'bg-warning-subtle text-warning',
    icon: <AlertTriangle size={14} />
  },
  critical: {
    bg: 'bg-danger-subtle text-danger',
    icon: <AlertCircle size={14} />
  },
};

// Category badge styles
const categoryStyles: Record<string, string> = {
  security: 'bg-danger-subtle text-danger',
  configuration: 'bg-purple-100 text-purple-800 dark:bg-purple-800 dark:text-purple-100', // css-check-ignore: no semantic token
  access: 'bg-success-subtle text-success',
  audit: 'bg-surface text-secondary',
};

// Action descriptions
const actionDescriptions: Record<string, string> = {
  create: 'Created',
  update: 'Updated',
  delete: 'Deleted',
  reveal: 'Revealed',
  login: 'Logged in',
  login_failed: 'Failed login',
  logout: 'Logged out',
  activate: 'Activated',
  deactivate: 'Deactivated',
  suspend: 'Suspended',
  view: 'Viewed',
  install: 'Installed',
  uninstall: 'Uninstalled',
  invite: 'Invited',
  role_change: 'Changed role',
  access_denied: 'Denied access to',
  download: 'Downloaded',
  token_refresh: 'Refreshed token for',
  trigger: 'Started',
  approve: 'Approved',
  reject: 'Rejected',
  bypass: 'Bypassed',
  timeout: 'Timed out on',
  cancel: 'Canceled',
  retry: 'Retried',
  rerun: 'Reran',
  regenerate: 'Regenerated',
  upload: 'Uploaded',
};

function AuditLogsContent() {
  const searchParams = useSearchParams();
  const { user } = useUser();

  const [activeCategory, setActiveCategory] = useListPref('audit', 'category', 'all', oneOf(CATEGORY_FILTERS));
  const [activeSeverity, setActiveSeverity] = useListPref('audit', 'severity', 'all', oneOf(SEVERITY_FILTERS));
  const [activeResourceType, setActiveResourceType] = useListPref('audit', 'resourceType', 'all', oneOf(RESOURCE_TYPE_FILTERS));

  // A filter in the address is applied once as the starting value.
  const [urlFiltersRead, setUrlFiltersRead] = useState(false);
  if (!urlFiltersRead) {
    setUrlFiltersRead(true);
    const category = searchParams.get('category');
    const severity = searchParams.get('severity');
    const resourceType = searchParams.get('resource_type');
    if (oneOf(CATEGORY_FILTERS)(category)) setActiveCategory(category);
    if (oneOf(SEVERITY_FILTERS)(severity)) setActiveSeverity(severity);
    if (oneOf(RESOURCE_TYPE_FILTERS)(resourceType)) setActiveResourceType(resourceType);
  }

  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());

  // Search and pagination state
  const [searchTerm, setSearchTerm] = useListPref('audit', 'search', '', isString);
  const [debouncedSearch, setDebouncedSearch] = useState(() => searchTerm.trim());
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useListPref('audit', 'pageSize', DEFAULT_PAGE_SIZE, isPageSize);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchTerm.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Determine if user has access
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';
  const isSuperAdmin = user?.role === 'super_admin';

  // Fetch audit events from API
  useEffect(() => {
    let stale = false;
    void (async () => {
      if (!user?.id || !isAdmin) {
        // Compute unconditionally; null clears any previous error.
        const permissionError = !isAdmin && user ? 'You do not have permission to view audit logs' : null;
        setError(permissionError);
        setLoading(false);
        return;
      }

      setLoading(true);
      try {
        const filters: AuditEventFilters = {
          skip: (currentPage - 1) * pageSize,
          limit: pageSize,
        };

        if (debouncedSearch) {
          filters.search = debouncedSearch;
        }
        if (activeCategory !== 'all') {
          filters.category = activeCategory;
        }
        if (activeSeverity !== 'all') {
          filters.severity = activeSeverity;
        }
        if (activeResourceType !== 'all') {
          filters.resource_type = activeResourceType;
        }

        const response = await getAuditEvents(filters);
        if (stale) return;
        setEvents(response.items);
        setTotalCount(response.total);
        setError(null);
      } catch (err: unknown) {
        if (stale) return;
        console.error('Failed to fetch audit events:', err);
        setError(err instanceof Error ? err.message : 'Failed to load audit events');
      } finally {
        if (!stale) setLoading(false);
      }
    })();
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- user?.id is sufficient, full user would cause extra re-renders
  }, [user?.id, isAdmin, currentPage, pageSize, debouncedSearch, activeCategory, activeSeverity, activeResourceType]);

  // Reset page when filters change (adjust during render, not in an effect).
  const filterKey = `${debouncedSearch}|${activeCategory}|${activeSeverity}|${activeResourceType}`;
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    setCurrentPage(1);
  }

  // Pagination calculations
  const totalPages = Math.ceil(totalCount / pageSize) || 1;

  // Toggle event expansion
  const toggleExpanded = (eventId: string) => {
    const newExpanded = new Set(expandedEvents);
    if (newExpanded.has(eventId)) {
      newExpanded.delete(eventId);
    } else {
      newExpanded.add(eventId);
    }
    setExpandedEvents(newExpanded);
  };

  // Format actor display
  const formatActor = (event: AuditEvent) => {
    const actorType = event.actor_type;
    if (actorType === 'system') return 'System';
    if (actorType === 'super_admin') return 'Super Admin';
    return actorType.charAt(0).toUpperCase() + actorType.slice(1);
  };

  // Format event description
  const formatEventDescription = (event: AuditEvent) => {
    const action = actionDescriptions[event.action] || event.action;
    const resourceType = resourceTypeName(event.resource_type);
    const resourceName = event.resource_name ? `"${event.resource_name}"` : '';

    return `${action} ${resourceType} ${resourceName}`.trim();
  };

  if (!isAdmin) {
    return (
      <>
        <div className="px-4 py-6 sm:px-6 lg:px-8">
          <ErrorState
            title="Access Denied"
            message="You do not have permission to view audit logs. Admin access required."
          />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        <div className="sm:flex sm:items-center mb-8">
          <div className="sm:flex-auto">
            <div className="flex items-center gap-2">
              <Shield className="h-6 w-6 text-secondary" />
              <h1 className="text-2xl font-semibold text-primary">Audit Logs</h1>
            </div>
            <p className="mt-2 text-sm text-secondary">
              View and monitor system activity and security events.
              {isSuperAdmin && ' As a super admin, you can see all organization and system events.'}
            </p>
          </div>
        </div>

        {!loading && error && (
          <ErrorState
            title="Error Loading Audit Logs"
            message={error}
            onRetry={() => window.location.reload()}
            retryLabel="Try Again"
          />
        )}

        {!error && (
          <div className="bg-card shadow overflow-hidden sm:rounded-md">
            {/* Filters Row */}
            <div className="border-b border-primary bg-card px-4 py-4 sm:px-6">
              <div className="flex flex-wrap gap-4">
                {/* Category Filter */}
                <div>
                  <label htmlFor="audit-category" className="block text-xs font-medium text-secondary mb-1">Category</label>
                  <select
                    id="audit-category"
                    value={activeCategory}
                    onChange={(e) => { const v = e.target.value; if (oneOf(CATEGORY_FILTERS)(v)) setActiveCategory(v); }}
                    className="form-select w-full text-sm"
                  >
                    <option value="all">All Categories</option>
                    <option value="security">Security</option>
                    <option value="configuration">Configuration</option>
                    <option value="access">Access</option>
                    <option value="audit">Audit</option>
                  </select>
                </div>

                {/* Severity Filter */}
                <div>
                  <label htmlFor="audit-severity" className="block text-xs font-medium text-secondary mb-1">Severity</label>
                  <select
                    id="audit-severity"
                    value={activeSeverity}
                    onChange={(e) => { const v = e.target.value; if (oneOf(SEVERITY_FILTERS)(v)) setActiveSeverity(v); }}
                    className="form-select w-full text-sm"
                  >
                    <option value="all">All Severities</option>
                    <option value="info">Info</option>
                    <option value="warning">Warning</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>

                {/* Resource Type Filter */}
                <div>
                  <label htmlFor="audit-resource-type" className="block text-xs font-medium text-secondary mb-1">Resource Type</label>
                  <select
                    id="audit-resource-type"
                    value={activeResourceType}
                    onChange={(e) => { const v = e.target.value; if (oneOf(RESOURCE_TYPE_FILTERS)(v)) setActiveResourceType(v); }}
                    className="form-select w-full text-sm"
                  >
                    <option value="all">All Types</option>
                    {RESOURCE_TYPE_FILTERS.filter((t) => t !== 'all').map((t) => (
                      <option key={t} value={t}>{resourceTypeLabels[t].many}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Search and Pagination Controls */}
            <div className="border-b border-primary bg-card px-4 py-4 sm:px-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <SearchInput
                  value={searchTerm}
                  onChange={setSearchTerm}
                  placeholder="Search names, actions and errors"
                />
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
                  pageSizeOptions={PAGE_SIZE_OPTIONS}
                  position="top"
                />
              </div>
            </div>

            {loading && (
              <div className="py-8">
                <LoadingState message="Loading audit events..." />
              </div>
            )}

            {/* Events List */}
            {!loading && (
            <ul className="divide-y divide-primary">
              {events.length > 0 ? (
                events.map((event) => {
                  const isExpanded = expandedEvents.has(event.id);
                  const severity = severityStyles[event.severity] || severityStyles.info;
                  const hasDetails = event.changes || (event.metadata && Object.keys(event.metadata).length > 0);

                  return (
                    <li
                      key={event.id}
                      className={`${event.severity === 'critical' ? 'bg-danger-subtle' : ''}`}
                    >
                      <div className="px-4 py-4 sm:px-6">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          <div className="flex items-center gap-3">
                            {/* Resource Type Icon */}
                            <div className="flex-shrink-0 text-muted dark:text-secondary">
                              {resourceTypeIcons[event.resource_type] || <Info size={16} />}
                            </div>

                            {/* Event Description */}
                            <div>
                              <p className="text-sm font-medium text-primary">
                                {formatEventDescription(event)}
                              </p>
                              <p className="text-xs text-secondary mt-0.5" title={event.actor_id ?? undefined}>
                                by {event.actor_name ? `${event.actor_name} (${formatActor(event)})` : formatActor(event)}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-3">
                            {/* Badges */}
                            <div className="flex items-center gap-2">
                              {/* Severity Badge */}
                              <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${severity.bg}`}>
                                {severity.icon}
                                {event.severity}
                              </span>

                              {/* Category Badge */}
                              <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${categoryStyles[event.category] || categoryStyles.configuration}`}>
                                {event.category}
                              </span>
                            </div>

                            {/* Timestamp */}
                            <p className="text-sm text-secondary whitespace-nowrap">
                              {formatDate(event.created_at)}
                            </p>
                          </div>
                        </div>

                        {/* Status indicator */}
                        {event.status === 'failed' && (
                          <div className="mt-2 text-xs text-danger">
                            Failed: {event.error_message || 'Unknown error'}
                          </div>
                        )}

                        {/* Expandable Details */}
                        {hasDetails && (
                          <div className="mt-3">
                            <button
                              onClick={() => toggleExpanded(event.id)}
                              className="flex items-center text-sm text-secondary hover:text-primary"
                            >
                              {isExpanded ? (
                                <ChevronDown className="h-4 w-4 mr-1" />
                              ) : (
                                <ChevronRight className="h-4 w-4 mr-1" />
                              )}
                              {isExpanded ? 'Hide details' : 'Show details'}
                            </button>

                            {isExpanded && (
                              <div className="mt-2 p-3 bg-surface rounded-md text-xs">
                                {event.changes && (
                                  <div className="mb-2">
                                    <span className="font-medium text-secondary">Changes:</span>
                                    <pre className="mt-1 text-secondary whitespace-pre-wrap">
                                      {JSON.stringify(event.changes, null, 2)}
                                    </pre>
                                  </div>
                                )}
                                {event.metadata && Object.keys(event.metadata).length > 0 && (
                                  <div>
                                    <span className="font-medium text-secondary">Metadata:</span>
                                    <pre className="mt-1 text-secondary whitespace-pre-wrap">
                                      {JSON.stringify(maskAuditMetadata(event.metadata), null, 2)}
                                    </pre>
                                  </div>
                                )}
                                {event.resource_id && (
                                  <div className="mt-2 text-secondary" title={`Identifier of the affected ${event.resource_type ? resourceTypeName(event.resource_type) : 'resource'} record`}>
                                    {event.resource_type ? `${resourceTypeName(event.resource_type).replace(/^./, (c) => c.toUpperCase())} ID` : 'Resource ID'}: {event.resource_id}
                                  </div>
                                )}
                                {isSuperAdmin && event.organization_id && (
                                  <div className="text-muted">
                                    Organization ID: {event.organization_id}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })
              ) : (
                <li className="py-8">
                  <EmptyState
                    icon={<Shield className="h-12 w-12" />}
                    title="No audit events found"
                    description={searchTerm ? 'Try adjusting your search term or filters.' : 'No events matching your filters.'}
                  />
                </li>
              )}
            </ul>
            )}

            {/* Pagination Controls - Bottom */}
            {!loading && events.length > 0 && (
              <div className="border-t border-primary bg-card px-4 py-4 sm:px-6">
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  totalCount={totalCount}
                  pageSize={pageSize}
                  onPageChange={setCurrentPage}
                  itemLabel="event"
                  position="bottom"
                />
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

export default function AuditLogsPage() {
  return (
    <Suspense fallback={
      <>
        <LoadingState message="Loading..." />
      </>
    }>
      <AuditLogsContent />
    </Suspense>
  );
}
