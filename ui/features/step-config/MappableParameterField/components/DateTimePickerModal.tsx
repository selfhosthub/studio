// ui/features/step-config/MappableParameterField/components/DateTimePickerModal.tsx

'use client';

import React, { useState } from 'react';
import DatePicker from 'react-datepicker';
import { Calendar, X } from 'lucide-react';
import { Modal } from '@/shared/ui';

export interface DateTimePickerModalProps {
  value: string;
  onChange: (value: string) => void;
  format?: 'date' | 'date-time';
  placeholder?: string;
}

function parseValue(value: string): Date | null {
  if (!value) return null;
  const dateOnly = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) {
    const [, y, m, d] = dateOnly;
    const local = new Date(Number(y), Number(m) - 1, Number(d));
    return isNaN(local.getTime()) ? null : local;
  }
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d;
}

function formatTrigger(date: Date | null, withTime: boolean): string {
  if (!date) return '';
  if (withTime) {
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function toOutputString(date: Date | null, withTime: boolean): string {
  if (!date) return '';
  if (withTime) return date.toISOString();
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function DateTimePickerModal({ value, onChange, format = 'date-time', placeholder }: DateTimePickerModalProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [tempDate, setTempDate] = useState<Date | null>(null);
  const withTime = format === 'date-time';
  const currentDate = parseValue(value);

  const openModal = () => {
    setTempDate(currentDate);
    setIsOpen(true);
  };

  const cancelModal = () => {
    setIsOpen(false);
  };

  const applyDate = () => {
    onChange(toOutputString(tempDate, withTime));
    setIsOpen(false);
  };

  const setNow = () => {
    setTempDate(new Date());
  };

  const clearDate = () => {
    setTempDate(null);
  };

  const triggerText = currentDate
    ? formatTrigger(currentDate, withTime)
    : (placeholder ?? (withTime ? 'Select date and time' : 'Select date'));

  return (
    <>
      <button
        type="button"
        onClick={openModal}
        title={withTime ? 'Open date and time picker' : 'Open date picker'}
        className="flex-1 p-2 border rounded text-sm text-left flex items-center gap-2 hover:bg-card"
      >
        <Calendar size={16} className="text-secondary" />
        <span className={currentDate ? '' : 'text-secondary'}>{triggerText}</span>
      </button>

      <Modal
        isOpen={isOpen}
        onClose={cancelModal}
        size="sm"
        panelClassName="w-auto max-w-[95vw] bg-card rounded-lg shadow-xl transition duration-200 ease-out data-[closed]:opacity-0 data-[closed]:scale-95"
      >
        <div className="p-4 studio-datepicker-theme">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-medium">{withTime ? 'Select Date & Time' : 'Select Date'}</h3>
            <button
              type="button"
              onClick={cancelModal}
              title="Close"
              className="text-secondary hover:text-secondary"
            >
              <X size={20} />
            </button>
          </div>

          <DatePicker
            selected={tempDate}
            onChange={(d: Date | null) => setTempDate(d)}
            showTimeSelect={withTime}
            timeIntervals={15}
            timeFormat="HH:mm"
            dateFormat={withTime ? 'yyyy-MM-dd HH:mm' : 'yyyy-MM-dd'}
            inline
          />

          <div className="flex gap-2 mt-4">
            <button
              type="button"
              onClick={clearDate}
              className="px-4 py-2 border rounded text-secondary hover:bg-card"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={setNow}
              className="px-4 py-2 border rounded text-secondary hover:bg-card"
            >
              Now
            </button>
            <button
              type="button"
              onClick={cancelModal}
              className="flex-1 px-4 py-2 border rounded text-secondary hover:bg-card"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={applyDate}
              className="btn-primary flex-1"
            >
              OK
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}

export default DateTimePickerModal;
