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

const DEFAULT_TTL_SECONDS = 900;

function formatQueues(queues: string[]): string {
  return queues.length ? queues.join(', ') : 'none'; // defaults-ok
}

function formatWhen(value: string | null): string {
  if (!value) return 'never';
  return new Date(value).toLocaleString();
}

export function WorkerEnrollmentPanel() {
  const [enrollments, setEnrollments] = useState<WorkerEnrollment[]>([]);
  const [label, setLabel] = useState('');
  const [queues, setQueues] = useState('');
  const [minted, setMinted] = useState<MintedJoinToken | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setEnrollments(await getWorkerEnrollments());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load enrollments');
    }
  }, []);

  useEffect(() => {
    void (async () => { await refresh(); })();
  }, [refresh]);

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

        {enrollments.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-theme">
              <thead className="bg-card">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">Worker</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">Queues</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">Last used</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-muted uppercase">Status</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-theme">
                {enrollments.map((e) => (
                  <tr key={e.id}>
                    <td className="px-4 py-2 text-sm">{e.label}</td>
                    <td className="px-4 py-2 text-sm text-muted">{formatQueues(e.queues)}</td>
                    <td className="px-4 py-2 text-sm text-muted">{formatWhen(e.last_used_at)}</td>
                    <td className="px-4 py-2 text-sm text-center">
                      {e.revoked_at ? (
                        <span className="text-muted">Revoked</span>
                      ) : (
                        <span className="text-success">Active</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {!e.revoked_at && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          aria-label={`Revoke ${e.label}`}
                          onClick={() => void handleRevoke(e)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted">
            No enrolled workers. Every worker is using the fleet shared secret.
          </p>
        )}
      </div>
    </div>
  );
}
