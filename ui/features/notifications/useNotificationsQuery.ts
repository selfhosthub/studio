// ui/features/notifications/useNotificationsQuery.ts

'use client';

import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getNotifications } from '@/shared/api';
import type { NotificationResponse } from '@/shared/types/api';
import { TIMEOUTS } from '@/shared/lib/constants';

export const notificationsQueryKey = (userId?: string) => ['notifications', userId] as const;

/** The recipient's notification list, shared by every component that shows it. */
export function useNotificationsQuery(userId?: string) {
  const { data, isLoading } = useQuery<NotificationResponse[]>({
    queryKey: notificationsQueryKey(userId),
    queryFn: async () => (await getNotifications(userId as string)) ?? [],
    enabled: Boolean(userId),
    staleTime: TIMEOUTS.NOTIFICATIONS_STALE,
  });

  return { notifications: data ?? [], loading: isLoading };
}

/** Marks the list stale so every mounted reader refetches once. */
export function useRefreshNotifications(userId?: string) {
  const queryClient = useQueryClient();
  return useCallback(
    () => queryClient.invalidateQueries({ queryKey: notificationsQueryKey(userId) }),
    [queryClient, userId]
  );
}

/** Applies a local edit to the cached list so the UI moves before the refetch lands. */
export function usePatchNotifications(userId?: string) {
  const queryClient = useQueryClient();
  return useCallback(
    (patch: (list: NotificationResponse[]) => NotificationResponse[]) =>
      queryClient.setQueryData<NotificationResponse[]>(
        notificationsQueryKey(userId),
        (prev) => patch(prev ?? [])
      ),
    [queryClient, userId]
  );
}
