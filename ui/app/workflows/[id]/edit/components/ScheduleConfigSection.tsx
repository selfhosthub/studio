// ui/app/workflows/[id]/edit/components/ScheduleConfigSection.tsx

'use client';

import React, { useState } from 'react';
import { setWorkflowSchedule, clearWorkflowSchedule } from '@/shared/api';
import { useToast } from '@/features/toast';
import {
  recurrenceToRrule,
  rruleToRecurrence,
  getBrowserTimezone,
  getTimezoneOptions,
  type RecurrenceChoice,
} from '@/shared/lib/schedule-utils';

interface ScheduleConfigSectionProps {
  workflowId: string;
  scheduleRrule: string | null;
  scheduleDtstart: string | null;
  scheduleTimezone: string | null;
  scheduleEnabled: boolean;
  scheduleNextRunAt: string | null;
  onSaved: (result: { enabled: boolean; next_run_at: string | null; rrule: string | null; dtstart: string | null; timezone: string }) => void;
  onCleared: () => void;
}

/** Converts a stored ISO datetime to a value usable by <input type="datetime-local">. */
function isoToLocalInput(iso: string | null): string {
  if (!iso) return '';
  // Trim seconds/timezone for the local input control.
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function ScheduleConfigSection({
  workflowId,
  scheduleRrule,
  scheduleDtstart,
  scheduleTimezone,
  scheduleEnabled,
  scheduleNextRunAt,
  onSaved,
  onCleared,
}: ScheduleConfigSectionProps) {
  const { toast } = useToast();

  const [dtstart, setDtstart] = useState<string>(isoToLocalInput(scheduleDtstart));
  const [timezone, setTimezone] = useState<string>(scheduleTimezone || getBrowserTimezone());
  const timezoneOptions = getTimezoneOptions(timezone);
  const [enabled, setEnabled] = useState<boolean>(scheduleEnabled);
  const [recurrence, setRecurrence] = useState<RecurrenceChoice>(rruleToRecurrence(scheduleRrule));
  const [customRrule, setCustomRrule] = useState<string>(
    rruleToRecurrence(scheduleRrule) === 'custom' ? (scheduleRrule || '') : '',
  );
  const [nextRunAt, setNextRunAt] = useState<string | null>(scheduleNextRunAt);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    const rrule = recurrenceToRrule(recurrence, customRrule);
    const dtstartIso = dtstart ? new Date(dtstart).toISOString() : null;

    // Form-input guard: a schedule needs at least a start time or a recurrence,
    // and an enabled schedule must have a concrete start time to compute next run.
    if (!dtstartIso && !rrule) {
      toast({ title: 'Schedule incomplete', description: 'Set a start time or a recurrence before saving.', variant: 'destructive' });
      return;
    }
    if (recurrence === 'custom' && !rrule) {
      toast({ title: 'RRULE required', description: 'Enter a recurrence rule or pick a different repeat option.', variant: 'destructive' });
      return;
    }
    if (enabled && !dtstartIso) {
      toast({ title: 'Start time required', description: 'An enabled schedule needs a start time.', variant: 'destructive' });
      return;
    }

    setSaving(true);
    try {
      const result = await setWorkflowSchedule(workflowId, {
        dtstart: dtstartIso,
        rrule,
        timezone,
        enabled,
      });
      setNextRunAt(result.next_run_at);
      onSaved({ ...result, rrule, dtstart: dtstartIso, timezone });
      toast({ title: 'Schedule saved', description: 'The workflow schedule was updated.', variant: 'success' });
    } catch (err: unknown) {
      toast({ title: 'Failed to save schedule', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    if (!confirm('Remove the schedule for this workflow? It will stop running automatically.')) {
      return;
    }
    setSaving(true);
    try {
      await clearWorkflowSchedule(workflowId);
      setDtstart('');
      setRecurrence('none');
      setCustomRrule('');
      setEnabled(false);
      setNextRunAt(null);
      onCleared();
      toast({ title: 'Schedule removed', description: 'This workflow will no longer run on a schedule.', variant: 'success' });
    } catch (err: unknown) {
      toast({ title: 'Failed to remove schedule', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="md:col-span-2 p-3 bg-surface rounded-md border border-primary">
      <div className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label htmlFor="schedule-dtstart" className="form-label">
              Start
            </label>
            <input
              id="schedule-dtstart"
              type="datetime-local"
              value={dtstart}
              onChange={(e) => setDtstart(e.target.value)}
              className="form-input mt-1"
            />
            <p className="form-helper">When the schedule begins (leave empty for now)</p>
          </div>

          <div>
            <label htmlFor="schedule-timezone" className="form-label">
              Timezone
            </label>
            <select
              id="schedule-timezone"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="form-select w-full mt-1"
            >
              {timezoneOptions.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
            <p className="form-helper">IANA timezone, e.g. America/Los_Angeles</p>
          </div>

          <div>
            <label htmlFor="schedule-recurrence" className="form-label">
              Repeats
            </label>
            <select
              id="schedule-recurrence"
              value={recurrence}
              onChange={(e) => setRecurrence(e.target.value as RecurrenceChoice)}
              className="form-select w-full mt-1"
            >
              <option value="none">Does not repeat</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
              <option value="custom">Custom (RRULE)</option>
            </select>
            <p className="form-helper">How often the workflow runs</p>
          </div>

          {recurrence === 'custom' && (
            <div>
              <label htmlFor="schedule-custom-rrule" className="form-label">
                RRULE
              </label>
              <input
                id="schedule-custom-rrule"
                type="text"
                value={customRrule}
                onChange={(e) => setCustomRrule(e.target.value)}
                placeholder="FREQ=WEEKLY;BYDAY=MO,WE,FR"
                className="form-input-mono mt-1"
              />
              <p className="form-helper">RFC 5545 recurrence rule (without RRULE: prefix)</p>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <input
            id="schedule-enabled"
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="form-checkbox"
          />
          <label htmlFor="schedule-enabled" className="text-sm text-secondary">
            Schedule enabled
          </label>
        </div>

        {nextRunAt && (
          <p className="form-helper">
            Next run: {new Date(nextRunAt).toLocaleString()}
          </p>
        )}

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn-primary text-xs px-3 py-1.5"
          >
            {saving ? 'Saving...' : 'Save schedule'}
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={saving}
            className="text-xs text-secondary hover:text-primary inline-flex items-center"
          >
            Remove schedule
          </button>
        </div>
      </div>
    </div>
  );
}
