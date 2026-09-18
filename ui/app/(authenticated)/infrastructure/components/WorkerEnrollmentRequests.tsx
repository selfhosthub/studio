// ui/app/(authenticated)/infrastructure/components/WorkerEnrollmentRequests.tsx

'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  approveEnrollmentRequest,
  getEnrollmentRequests,
  rejectEnrollmentRequest,
  type EnrollmentRequest,
  type EnrollmentRequestStatus,
} from '@/shared/api';
import { ErrorState, LoadingState, Modal, StatusBadge } from '@/shared/ui';

type Decision = { request: EnrollmentRequest; kind: 'approve' | 'reject' };

const STATUS_VARIANT: Record<EnrollmentRequestStatus, 'warning' | 'success' | 'error' | 'info'> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'error',
  claimed: 'info',
};

function formatQueues(queues: string[]): string {
  return queues.length ? queues.join(', ') : 'none'; // defaults-ok
}

function formatWhere(request: EnrollmentRequest): string {
  return [request.hostname, request.ip_address].filter(Boolean).join(' · ') || '-'; // defaults-ok
}

interface WorkerEnrollmentRequestsProps {
  onDecided: () => Promise<void> | void;
  // New identity on each page refresh; reloads the list.
  refreshSignal?: unknown;
}

export function WorkerEnrollmentRequests({ onDecided, refreshSignal }: WorkerEnrollmentRequestsProps) {
  const [requests, setRequests] = useState<EnrollmentRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [granted, setGranted] = useState<string[]>([]);
  const [decideError, setDecideError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setRequests(await getEnrollmentRequests());
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Could not load enrollment requests');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void (async () => { await load(); })();
  }, [load, refreshSignal]);

  const open = (request: EnrollmentRequest, kind: Decision['kind']) => {
    setDecision({ request, kind });
    setGranted(request.queues);
    setDecideError(null);
  };

  const close = () => {
    if (!busy) setDecision(null);
  };

  const toggleQueue = (queue: string) => {
    setGranted((current) =>
      current.includes(queue) ? current.filter((q) => q !== queue) : [...current, queue]
    );
  };

  const confirm = async () => {
    if (!decision) return;
    setBusy(true);
    setDecideError(null);
    try {
      if (decision.kind === 'approve') {
        await approveEnrollmentRequest(decision.request.id, granted);
      } else {
        await rejectEnrollmentRequest(decision.request.id);
      }
      setDecision(null);
      await Promise.all([load(), onDecided()]);
    } catch (e) {
      setDecideError(e instanceof Error ? e.message : 'Could not record the decision');
    } finally {
      setBusy(false);
    }
  };

  const pending = requests.filter((r) => r.status === 'pending');
  const decided = requests.filter((r) => r.status !== 'pending');

  return (
    <div className="mb-6">
      <h3 className="text-sm font-semibold text-primary">Pending requests</h3>
      <p className="text-sm text-muted mb-3">
        A worker outside this deployment that registered with the shared secret waits here until
        approved. Approving gives it its own revocable credential.
      </p>

      {loading ? (
        <LoadingState message="Loading enrollment requests..." className="py-4" />
      ) : loadError ? (
        <ErrorState
          title="Could not load enrollment requests"
          message={loadError}
          onRetry={() => void load()}
        />
      ) : (
        <>
          {pending.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-theme">
                <thead className="bg-card">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">Worker</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">Host</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">Queues</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">Requested</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-theme">
                  {pending.map((r) => (
                    <tr key={r.id}>
                      <td className="px-4 py-2 text-sm">{r.name}</td>
                      <td className="px-4 py-2 text-sm text-muted">{formatWhere(r)}</td>
                      <td className="px-4 py-2 text-sm text-muted">{formatQueues(r.queues)}</td>
                      <td className="px-4 py-2 text-sm text-muted">
                        {new Date(r.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right whitespace-nowrap">
                        <button
                          type="button"
                          className="btn btn-primary mr-2"
                          aria-label={`Approve ${r.name}`}
                          onClick={() => open(r, 'approve')}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          aria-label={`Reject ${r.name}`}
                          onClick={() => open(r, 'reject')}
                        >
                          Reject
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted">No workers are waiting for approval.</p>
          )}

          {decided.length > 0 && (
            <details className="mt-3">
              <summary className="text-sm text-secondary cursor-pointer">
                Recently decided ({decided.length})
              </summary>
              <ul className="mt-2 divide-y divide-theme">
                {decided.map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-4 py-2 text-sm">
                    <span>
                      {r.name}
                      <span className="ml-2 text-muted">{formatQueues(r.queues)}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      {r.decided_at && (
                        <span className="text-xs text-muted">
                          {new Date(r.decided_at).toLocaleString()}
                        </span>
                      )}
                      <StatusBadge status={r.status} variant={STATUS_VARIANT[r.status]} />
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}

      <Modal
        isOpen={decision !== null}
        onClose={close}
        title={decision?.kind === 'approve' ? 'Approve worker' : 'Reject worker'}
        size="sm"
      >
        {decision && (
          <div className="p-6">
            {decision.kind === 'approve' ? (
              <fieldset>
                <legend className="text-sm text-secondary mb-3">
                  Grant {decision.request.name} a credential for these queues:
                </legend>
                {decision.request.queues.map((queue) => (
                  <label key={queue} className="flex items-center gap-2 text-sm mb-2">
                    <input
                      type="checkbox"
                      className="form-checkbox"
                      checked={granted.includes(queue)}
                      onChange={() => toggleQueue(queue)}
                    />
                    {queue}
                  </label>
                ))}
              </fieldset>
            ) : (
              <p className="text-sm text-secondary">
                Reject {decision.request.name}? It will not receive a credential.
              </p>
            )}

            {decideError && (
              <div className="mt-4 bg-error-subtle border border-error rounded-md p-3 text-sm text-error" role="alert">
                {decideError}
              </div>
            )}

            <div className="mt-6 flex justify-end gap-3">
              <button type="button" className="btn-secondary" disabled={busy} onClick={close}>
                Cancel
              </button>
              <button
                type="button"
                className={decision.kind === 'approve' ? 'btn-primary' : 'btn-danger'}
                disabled={busy || (decision.kind === 'approve' && granted.length === 0)}
                onClick={() => void confirm()}
              >
                {decision.kind === 'approve'
                  ? busy ? 'Approving...' : 'Approve'
                  : busy ? 'Rejecting...' : 'Reject'}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
