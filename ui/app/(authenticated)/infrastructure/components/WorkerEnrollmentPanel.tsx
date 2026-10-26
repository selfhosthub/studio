// ui/app/(authenticated)/infrastructure/components/WorkerEnrollmentPanel.tsx

'use client';

import { useCallback, useEffect, useState } from 'react';
import { KeyRound, Trash2 } from 'lucide-react';
import {
  getWorkerEnrollments,
  mintJoinToken,
  revokeWorkerEnrollment,
  type MintedJoinToken,
  type WorkerEnrollment,
} from '@/shared/api';
import { ResourceTable } from '@/shared/ui';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import { WorkerEnrollmentRequests } from './WorkerEnrollmentRequests';
import { formatDate } from '@/shared/lib/dateFormatter';

const DEFAULT_TTL_SECONDS = 900;

function formatQueues(queues: string[]): string {
  return queues.length ? queues.join(', ') : 'none'; // defaults-ok
}

function formatWhen(value: string | null): string {
  if (!value) return 'never';
  return formatDate(value);
}

interface WorkerEnrollmentPanelProps {
  // New identity on each page refresh; reloads the credentials and the requests below.
  refreshSignal?: unknown;
}

export function WorkerEnrollmentPanel({ refreshSignal }: WorkerEnrollmentPanelProps) {
  const [enrollments, setEnrollments] = useState<WorkerEnrollment[]>([]);
  const [label, setLabel] = useState('');
  const [queues, setQueues] = useState('');
  const [minted, setMinted] = useState<MintedJoinToken | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  const refresh = useCallback(async () => {
    try {
      setEnrollments(await getWorkerEnrollments());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load enrollments');
    }
  }, []);

  useEffect(() => {
    void (async () => { await refresh(); })();
  }, [refresh, refreshSignal]);

  const handleMint = async () => {
    setBusy(true);
    setError(null);
    setMinted(null);
    try {
      const parsed = queues
        .split(',')
        .map((q) => q.trim())
        .filter(Boolean);
      setMinted(await mintJoinToken(label, parsed, DEFAULT_TTL_SECONDS));
      setLabel('');
      setQueues('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not mint a join token');
    } finally {
      setBusy(false);
    }
  };

  const handleRevoke = async (enrollment: WorkerEnrollment) => {
    const confirmed = await confirm({
      title: 'Revoke credential',
      message: `Revoke the credential for "${enrollment.label}"?`,
      confirmLabel: 'Revoke',
      variant: 'danger',
    });
    if (!confirmed) return;
    setError(null);
    try {
      await revokeWorkerEnrollment(enrollment.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not revoke the credential');
    }
  };

  return (
    <div className="detail-section detail-section-green mt-6">
      <div className="detail-section-header flex justify-between items-center">
        <h2 className="section-title flex items-center">
          <KeyRound className="w-5 h-5 mr-2 text-success" />
          Worker Enrollment
        </h2>
        <span className="section-subtitle">
          Give one worker its own revocable credential instead of the fleet secret
        </span>
      </div>
      <div className="detail-section-body">
        {error && (
          <div className="mb-4 bg-error-subtle border border-error rounded-md p-3 text-sm text-error" role="alert">
            {error}
          </div>
        )}

        <WorkerEnrollmentRequests onDecided={refresh} refreshSignal={refreshSignal} />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <input
            className="input"
            placeholder="Worker name, e.g. gpu-box-2"
            aria-label="Worker name"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <input
            className="input"
            placeholder="Queues, comma separated"
            aria-label="Queues"
            value={queues}
            onChange={(e) => setQueues(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !label.trim()}
            onClick={() => void handleMint()}
          >
            {busy ? 'Minting...' : 'Mint join token'}
          </button>
        </div>

        {minted && (
          <div className="mb-6 bg-warning-subtle border border-warning rounded-md p-3" role="status">
            <p className="text-sm text-warning mb-2">
              Copy this now. It is shown once, expires {formatWhen(minted.expires_at)}, and works for one worker.
            </p>
            <code className="block break-all text-sm">
              studio-workers enroll --join-token {minted.token}
            </code>
          </div>
        )}

        <ResourceTable
          data={enrollments}
          getItemId={(e) => e.id}
          tieBreaker="worker"
          prefPage="infra-enrollment"
          pagination={{ itemLabel: 'credential' }}
          containerClassName="mb-0"
          emptyState={
            <p className="text-sm text-muted">
              No enrolled workers. Every worker is using the fleet shared secret.
            </p>
          }
          columns={[
            { key: 'worker', header: 'Worker', headerClassName: 'text-muted', sortValue: (e) => e.label, render: (e) => e.label },
            { key: 'queues', header: 'Queues', headerClassName: 'text-muted', cellClassName: 'text-muted', sortValue: (e) => e.queues.join(', '), render: (e) => formatQueues(e.queues) },
            {
              key: 'last_used',
              header: 'Last used',
              headerClassName: 'text-muted',
              cellClassName: 'text-muted',
              sortValue: (e) => (e.last_used_at ? new Date(e.last_used_at) : null),
              render: (e) => formatWhen(e.last_used_at),
            },
            {
              key: 'status',
              header: 'Status',
              align: 'center',
              headerClassName: 'text-muted',
              sortValue: (e) => (e.revoked_at ? 'Revoked' : 'Active'),
              render: (e) => (
                e.revoked_at ? (
                  <span className="text-muted">Revoked</span>
                ) : (
                  <span className="text-success">Active</span>
                )
              ),
            },
            {
              key: 'actions',
              header: '',
              align: 'right',
              render: (e) => (
                !e.revoked_at && (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    aria-label={`Revoke ${e.label}`}
                    onClick={() => void handleRevoke(e)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
