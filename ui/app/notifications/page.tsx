// ui/app/notifications/page.tsx

'use client';

import { DashboardLayout } from "@/widgets/layout";
import { useUser } from '@/entities/user';
import { useState, useEffect, useMemo, useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { formatDate } from '@/shared/lib/dateFormatter';
import { getNotifications, markNotificationAsRead, markAllNotificationsAsRead } from '@/shared/api';
import { useNotificationWebSocket } from '@/features/notifications/hooks/useNotificationWebSocket';
import { PAGINATION } from '@/shared/lib/constants';
import Link from 'next/link';
import { ChevronDown, ChevronRight, Bell, CheckCheck } from 'lucide-react';
import {
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
} from '@/shared/ui';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';


function NotificationsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useUser();
  const userId = user?.id;
  const activeFilter = searchParams.get('filter') || 'all';
  const [notifications, setNotifications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedNotifications, setExpandedNotifications] = useState<Set<string>>(new Set());

  // Search and pagination state
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGINATION.DEFAULT_PAGE_SIZE);

  // WebSocket for real-time updates
  const { lastEvent } = useNotificationWebSocket();

  // Fetch notifications from API
  const fetchNotifications = useCallback(() => {
    if (!userId) return;
    getNotifications(userId)
      .then((data) => {
        setNotifications(data);
        setError(null);
      })
      .catch(() => {
        setError('Failed to load notifications');
      })
      .finally(() => setLoading(false));
  }, [userId]);

  // Initial fetch
  useEffect(() => {
    if (!userId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError('No user ID found');
      setLoading(false);
      return;
    }
    fetchNotifications();
  }, [userId, fetchNotifications]);

  // Refetch on WebSocket notification events
  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.event_type === 'notification_created' || lastEvent.event_type === 'notification_read') {
      fetchNotifications();
    }
  }, [lastEvent, fetchNotifications]);

  // Helper to extract metadata from notification
  const getMetadata = (notification: any) => {
    return notification.client_metadata || {};
  };

  // Helper to determine if notification is read
  const isRead = useCallback((notification: any) => {
    return notification.read_at != null;
  }, []);

  // Helper to get category from tags or metadata
  const getCategory = useCallback((notification: any) => {
    const tags = notification.tags || [];
    if (tags.includes('workflow')) return 'workflow';
    if (tags.includes('job')) return 'job';
    if (tags.includes('system')) return 'system';
    if (tags.includes('account')) return 'account';
    if (tags.includes('security')) return 'security';
    if (tags.includes('billing')) return 'billing';
    const metadata = getMetadata(notification);
    if (metadata.workflow_id || metadata.instance_id) return 'workflow';
    return 'other';
  }, []);

  // Filter notifications based on active filter and search
  const filteredNotifications = useMemo(() => {
    let result = notifications;

    // Apply category/status filter
    if (activeFilter === 'unread') {
      result = result.filter(n => !isRead(n));
    } else if (activeFilter !== 'all') {
      result = result.filter(n => getCategory(n) === activeFilter);
    }

    // Apply search filter
    if (searchTerm) {
      const query = searchTerm.toLowerCase();
      result = result.filter(n =>
        n.title?.toLowerCase().includes(query) ||
        n.message?.toLowerCase().includes(query) ||
        n.content?.toLowerCase().includes(query)
      );
    }

    return result;
  }, [notifications, activeFilter, searchTerm, isRead, getCategory]);

  // Reset page when filters change
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurrentPage(1);
  }, [searchTerm, activeFilter]);

  // Pagination calculations
  const totalCount = filteredNotifications.length;
  const totalPages = Math.ceil(totalCount / pageSize) || 1;

  // Apply pagination
  const paginatedNotifications = filteredNotifications.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  // Handle marking notification as read
  const handleMarkAsRead = async (notificationId: string) => {
    try {
      await markNotificationAsRead(notificationId);
      setNotifications(notifications.map(n =>
        n.id === notificationId ? { ...n, read_at: new Date().toISOString() } : n
      ));
    } catch {
      // Silently fail if marking as read fails
    }
  };

  // Handle marking all notifications as read
  const handleMarkAllAsRead = async () => {
    if (!userId) return;
    try {
      await markAllNotificationsAsRead(userId);
      const now = new Date().toISOString();
      setNotifications(notifications.map(n =>
        n.read_at ? n : { ...n, read_at: now }
      ));
    } catch {
      // Silently fail
    }
  };

  // Toggle notification expansion
  const toggleExpanded = (notificationId: string) => {
    const newExpanded = new Set(expandedNotifications);
    if (newExpanded.has(notificationId)) {
      newExpanded.delete(notificationId);
    } else {
      newExpanded.add(notificationId);
    }
    setExpandedNotifications(newExpanded);
  };

  // Generate detail link based on notification context
  const getDetailLink = (notification: any) => {
    const metadata = getMetadata(notification);

    // First check for action_url which is the preferred navigation target
    if (notification.action_url) {
      return notification.action_url;
    }
    // Check client_metadata for IDs
    if (metadata.instance_id) {
      return `/instances/${metadata.instance_id}`;
    }
    if (metadata.workflow_id) {
      return `/workflows/${metadata.workflow_id}`;
    }
    if (metadata.blueprint_id || metadata.template_id) {
      return `/blueprints/${metadata.blueprint_id || metadata.template_id}`;
    }
    // Older notifications store entity IDs on the root object rather than in metadata
    if (notification.workflow_id) {
      return `/workflows/${notification.workflow_id}`;
    }
    if (notification.instance_id) {
      return `/instances/${notification.instance_id}`;
    }
    return null;
  };

  // Get related notifications (same context)
  const getRelatedNotifications = (notification: any) => {
    const metadata = getMetadata(notification);
    const workflowId = metadata.workflow_id || notification.workflow_id;
    const instanceId = metadata.instance_id || notification.instance_id;
    const blueprintId = metadata.blueprint_id || metadata.template_id;

    if (!workflowId && !instanceId && !blueprintId) {
      return [];
    }

    return notifications.filter(n => {
      if (n.id === notification.id) return false;
      const nMeta = getMetadata(n);
      const nWorkflowId = nMeta.workflow_id || n.workflow_id;
      const nInstanceId = nMeta.instance_id || n.instance_id;
      const nBlueprintId = nMeta.blueprint_id || nMeta.template_id;
      return (
        (workflowId && nWorkflowId === workflowId) ||
        (instanceId && nInstanceId === instanceId) ||
        (blueprintId && nBlueprintId === blueprintId)
      );
    });
  };

  // Define category badge colors
  const categoryColors: Record<string, string> = {
    workflow: 'bg-info-subtle text-info',
    job: 'bg-purple-100 text-purple-800 dark:bg-purple-800 dark:text-purple-100',
    system: 'bg-warning-subtle text-warning',
    account: 'bg-success-subtle text-success',
    security: 'bg-danger-subtle text-danger',
    billing: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-800 dark:text-indigo-100',
    other: 'bg-card text-primary'
  };

  return (
    <DashboardLayout>
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        <div className="sm:flex sm:items-center mb-8">
          <div className="sm:flex-auto">
            <h1 className="text-2xl font-semibold text-primary">Notifications</h1>
            <p className="mt-2 section-subtitle">
              View and manage your system notifications.
            </p>
          </div>
          {notifications.some(n => !n.read_at) && (
            <div className="mt-4 sm:ml-16 sm:mt-0 sm:flex-none">
              <button
                onClick={handleMarkAllAsRead}
                className="flex items-center gap-2 btn-primary rounded-md px-3 py-2 text-sm font-semibold shadow-sm"
              >
                <CheckCheck size={16} />
                Mark all as read
              </button>
            </div>
          )}
        </div>

        {loading && (
          <LoadingState message="Loading notifications..." />
        )}

        {!loading && error && (
          <ErrorState
            title="Error Loading Notifications"
            message={error}
            onRetry={() => window.location.reload()}
            retryLabel="Try Again"
          />
        )}

        {!loading && !error && (
          <div className="bg-card shadow overflow-hidden sm:rounded-md">
            <div className="border-b border-primary bg-card px-4 py-4 sm:px-6">
              <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-4 px-4 sm:mx-0 sm:px-0">
                <button
                  onClick={() => router.push('/notifications?filter=all')}
                  className={`filter-pill ${activeFilter === 'all' ? 'filter-pill-active' : 'filter-pill-inactive'}`}
                >
                  All
                </button>
                <button
                  onClick={() => router.push('/notifications?filter=unread')}
                  className={`filter-pill ${activeFilter === 'unread' ? 'filter-pill-active' : 'filter-pill-inactive'}`}
                >
                  Unread
                </button>
                <button
                  onClick={() => router.push('/notifications?filter=workflow')}
                  className={`filter-pill ${activeFilter === 'workflow' ? 'filter-pill-active' : 'filter-pill-inactive'}`}
                >
                  Workflow
                </button>
                <button
                  onClick={() => router.push('/notifications?filter=job')}
                  className={`filter-pill ${activeFilter === 'job' ? 'filter-pill-active' : 'filter-pill-inactive'}`}
                >
                  Job
                </button>
                <button
                  onClick={() => router.push('/notifications?filter=system')}
                  className={`filter-pill ${activeFilter === 'system' ? 'filter-pill-active' : 'filter-pill-inactive'}`}
                >
                  System
                </button>
                <button
                  onClick={() => router.push('/notifications?filter=account')}
                  className={`filter-pill ${activeFilter === 'account' ? 'filter-pill-active' : 'filter-pill-inactive'}`}
                >
                  Account
                </button>
              </div>
            </div>

            {/* Search and Pagination Controls */}
            <div className="border-b border-primary bg-card px-4 py-4 sm:px-6">
              <div className="flex items-center justify-between gap-4">
                <SearchInput
                  value={searchTerm}
                  onChange={setSearchTerm}
                  placeholder="Search notifications..."
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

            <ul className="divide-y divide-primary">
              {paginatedNotifications.length > 0 ? (
                paginatedNotifications.map((notification) => {
                  const detailLink = getDetailLink(notification);
                  const relatedNotifs = getRelatedNotifications(notification);
                  const isExpanded = expandedNotifications.has(notification.id);

                  return (
                    <li
                      key={notification.id}
                      className={`${!isRead(notification) ? 'bg-info-subtle' : ''}`}
                    >
                      <div className="px-4 py-4 sm:px-6">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center">
                            {detailLink ? (
                              <Link
                                href={detailLink}
                                onClick={() => !isRead(notification) && handleMarkAsRead(notification.id)}
                                className="text-sm font-medium link truncate hover:underline"
                              >
                                {notification.title}
                              </Link>
                            ) : (
                              <p className="text-sm font-medium text-primary truncate">{notification.title}</p>
                            )}
                            <div className={`ml-2 flex-shrink-0 flex`}>
                              <p className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${categoryColors[getCategory(notification)]}`}>
                                {getCategory(notification)}
                              </p>
                            </div>
                          </div>
                          <div className="ml-2 flex-shrink-0 flex">
                            <p className="text-muted">
                              {formatDate(notification.created_at)}
                            </p>
                          </div>
                        </div>
                        <div className="mt-2 sm:flex sm:justify-between">
                          <div className="sm:flex flex-1">
                            <p className="text-muted">{notification.message || notification.content}</p>
                          </div>
                          <div className="mt-2 flex items-center gap-3 text-sm text-secondary sm:mt-0">
                            {!isRead(notification) ? (
                              <button
                                onClick={() => handleMarkAsRead(notification.id)}
                                className="link"
                              >
                                Mark as read
                              </button>
                            ) : (
                              <span className="text-muted dark:text-secondary">Read</span>
                            )}
                          </div>
                        </div>

                        {/* Workflow/Instance Details from metadata */}
                        {(() => {
                          const metadata = getMetadata(notification);
                          const hasMetadata = metadata.workflow_id || metadata.instance_id || metadata.error;
                          if (!hasMetadata) return null;
                          return (
                            <div className="mt-2 text-xs text-secondary space-x-4">
                              {metadata.workflow_id && (
                                <span>
                                  <span className="font-medium">Workflow:</span>{' '}
                                  <Link href={`/workflows/${metadata.workflow_id}`} className="link hover:underline">
                                    {metadata.workflow_name || metadata.workflow_id.slice(0, 8) + '...'}
                                  </Link>
                                </span>
                              )}
                              {metadata.instance_id && (
                                <span>
                                  <span className="font-medium">Instance:</span>{' '}
                                  <Link href={`/instances/${metadata.instance_id}`} className="link hover:underline">
                                    View
                                  </Link>
                                </span>
                              )}
                              {metadata.error && (
                                <span className="text-danger">
                                  <span className="font-medium">Error:</span> {metadata.error}
                                </span>
                              )}
                            </div>
                          );
                        })()}

                        {/* Additional Details */}
                        {notification.additional_details && (
                          <div className="mt-2 text-xs text-secondary">
                            {Object.entries(notification.additional_details).map(([key, value]) => (
                              <div key={key} className="inline-block mr-4">
                                <span className="font-medium capitalize">{key.replace(/_/g, ' ')}:</span> {String(value)}
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Related Notifications */}
                        {relatedNotifs.length > 0 && (
                          <div className="mt-3 border-t border-primary pt-3">
                            <button
                              onClick={() => toggleExpanded(notification.id)}
                              className="flex items-center text-sm text-secondary hover:text-primary"
                            >
                              {isExpanded ? (
                                <ChevronDown className="h-4 w-4 mr-1" />
                              ) : (
                                <ChevronRight className="h-4 w-4 mr-1" />
                              )}
                              {relatedNotifs.length} related notification{relatedNotifs.length !== 1 ? 's' : ''}
                            </button>

                            {isExpanded && (
                              <div className="mt-2 ml-5 space-y-2">
                                {relatedNotifs.map((related) => (
                                  <div
                                    key={related.id}
                                    className="text-xs bg-card p-2 rounded"
                                  >
                                    <div className="flex items-center justify-between">
                                      <span className="font-medium text-secondary">
                                        {related.title}
                                      </span>
                                      <span className="text-muted">
                                        {formatDate(related.created_at)}
                                      </span>
                                    </div>
                                    <p className="mt-1 text-secondary">{related.message || related.content}</p>
                                  </div>
                                ))}
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
                    icon={<Bell className="h-12 w-12" />}
                    title="No notifications found"
                    description={searchTerm ? 'Try adjusting your search term.' : 'No notifications matching your filter.'}
                  />
                </li>
              )}
            </ul>

            {/* Pagination Controls - Bottom */}
            {paginatedNotifications.length > 0 && (
              <div className="border-t border-primary bg-card px-4 py-4 sm:px-6">
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  totalCount={totalCount}
                  pageSize={pageSize}
                  onPageChange={setCurrentPage}
                  itemLabel="notification"
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

export default function NotificationsPage() {
  return (
    <Suspense fallback={
      <DashboardLayout>
        <LoadingState message="Loading..." />
      </DashboardLayout>
    }>
      <NotificationsContent />
    </Suspense>
  );
}
