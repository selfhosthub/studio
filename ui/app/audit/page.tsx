// ui/app/audit/page.tsx

'use client';

import { DashboardLayout } from "@/widgets/layout";
import { useUser } from '@/entities/user';
import { useState, useEffect, useMemo, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { formatDate } from '@/shared/lib/dateFormatter';
import { getAuditEvents, AuditEvent } from '@/shared/api';
import { PAGINATION } from '@/shared/lib/constants';
import {
  Shield,
  AlertTriangle,
  Info,
  AlertCircle,
  User,
  Key,
  Building2,
  Workflow,
  FileCode2,
  PlayCircle,
  Plug,
  Package,
  Eye,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import {
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
} from '@/shared/ui';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';

// Resource type icons
const resourceTypeIcons: Record<string, React.ReactNode> = {
  secret: <Key size={16} />,
  credential: <Key size={16} />,
  user: <User size={16} />,
  organization: <Building2 size={16} />,
  workflow: <Workflow size={16} />,
  template: <FileCode2 size={16} />,
  instance: <PlayCircle size={16} />,
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
  audit: 'bg-card text-primary',
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
};

function AuditLogsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useUser();

  // Filters from URL
  const activeCategory = searchParams.get('category') || 'all';
  const activeSeverity = searchParams.get('severity') || 'all';
  const activeResourceType = searchParams.get('resource_type') || 'all';

  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());

  // Search and pagination state
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGINATION.DEFAULT_PAGE_SIZE);

  // Determine if user has access
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';
  const isSuperAdmin = user?.role === 'super_admin';

  // Fetch audit events from API
  useEffect(() => {
    if (!user?.id || !isAdmin) {
      if (!isAdmin && user) {
        setError('You do not have permission to view audit logs');
      }
      setLoading(false);
      return;
    }

    const fetchEvents = async () => {
      setLoading(true);
      try {
        const filters: Record<string, any> = {
          skip: (currentPage - 1) * pageSize,
          limit: pageSize,
        };

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
        setEvents(response.items);
        setTotalCount(response.total);
        setError(null);
      } catch (err: unknown) {
        console.error('Failed to fetch audit events:', err);
        setError(err instanceof Error ? err.message : 'Failed to load audit events');
      } finally {
        setLoading(false);
      }
    };

    fetchEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- user?.id is sufficient, full user would cause extra re-renders
  }, [user?.id, isAdmin, currentPage, pageSize, activeCategory, activeSeverity, activeResourceType]);

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, activeCategory, activeSeverity, activeResourceType]);

  // Client-side search filter
  const filteredEvents = useMemo(() => {
    if (!searchTerm) return events;

    const query = searchTerm.toLowerCase();
    return events.filter(event =>
      event.resource_name?.toLowerCase().includes(query) ||
      event.action.toLowerCase().includes(query) ||
      event.resource_type.toLowerCase().includes(query) ||
      event.actor_type.toLowerCase().includes(query)
    );
  }, [events, searchTerm]);

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

  // Update URL with filters
  const setFilter = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === 'all') {
      params.delete(key);
    } else {
      params.set(key, value);
    }
    router.push(`/audit?${params.toString()}`);
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
    const resourceType = event.resource_type.replace(/_/g, ' ');
    const resourceName = event.resource_name ? `"${event.resource_name}"` : '';

    return `${action} ${resourceType} ${resourceName}`.trim();
  };

  if (!isAdmin) {
    return (
      <DashboardLayout>
        <div className="px-4 py-6 sm:px-6 lg:px-8">
          <ErrorState
            title="Access Denied"
            message="You do not have permission to view audit logs. Admin access required."
          />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
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

        {loading && (
          <LoadingState message="Loading audit events..." />
        )}

        {!loading && error && (
          <ErrorState
            title="Error Loading Audit Logs"
            message={error}
            onRetry={() => window.location.reload()}
            retryLabel="Try Again"
          />
        )}

        {!loading && !error && (
          <div className="bg-card shadow overflow-hidden sm:rounded-md">
            {/* Filters Row */}
            <div className="border-b border-primary bg-card px-4 py-4 sm:px-6">
              <div className="flex flex-wrap gap-4">
                {/* Category Filter */}
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Category</label>
                  <select
                    value={activeCategory}
                    onChange={(e) => setFilter('category', e.target.value)}
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
                  <label className="block text-xs font-medium text-secondary mb-1">Severity</label>
                  <select
                    value={activeSeverity}
                    onChange={(e) => setFilter('severity', e.target.value)}
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
                  <label className="block text-xs font-medium text-secondary mb-1">Resource Type</label>
                  <select
                    value={activeResourceType}
                    onChange={(e) => setFilter('resource_type', e.target.value)}
                    className="form-select w-full text-sm"
                  >
                    <option value="all">All Types</option>
                    <option value="secret">Secrets</option>
                    <option value="credential">Credentials</option>
                    <option value="user">Users</option>
                    <option value="organization">Organizations</option>
                    <option value="workflow">Workflows</option>
                    <option value="template">Templates</option>
                    <option value="instance">Instances</option>
                    <option value="provider">Providers</option>
                    <option value="package">Packages</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Search and Pagination Controls */}
            <div className="border-b border-primary bg-card px-4 py-4 sm:px-6">
              <div className="flex items-center justify-between gap-4">
                <SearchInput
                  value={searchTerm}
                  onChange={setSearchTerm}
                  placeholder="Search events..."
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

            {/* Events List */}
            <ul className="divide-y divide-primary">
              {filteredEvents.length > 0 ? (
                filteredEvents.map((event) => {
                  const isExpanded = expandedEvents.has(event.id);
                  const severity = severityStyles[event.severity] || severityStyles.info;
                  const hasDetails = event.changes || (event.metadata && Object.keys(event.metadata).length > 0);

                  return (
                    <li
                      key={event.id}
                      className={`${event.severity === 'critical' ? 'bg-danger-subtle' : ''}`}
                    >
                      <div className="px-4 py-4 sm:px-6">
                        <div className="flex items-center justify-between">
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
                              <p className="text-xs text-secondary mt-0.5">
                                by {formatActor(event)} {event.actor_id && `(${event.actor_id.slice(0, 8)}...)`}
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
                                      {JSON.stringify(event.metadata, null, 2)}
                                    </pre>
                                  </div>
                                )}
                                {event.resource_id && (
                                  <div className="mt-2 text-secondary">
                                    Resource ID: {event.resource_id}
                                  </div>
                                )}
                                {event.organization_id && (
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

            {/* Pagination Controls - Bottom */}
            {filteredEvents.length > 0 && (
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
    </DashboardLayout>
  );
}

export default function AuditLogsPage() {
  return (
    <Suspense fallback={
      <DashboardLayout>
        <LoadingState message="Loading..." />
      </DashboardLayout>
    }>
      <AuditLogsContent />
    </Suspense>
  );
}
