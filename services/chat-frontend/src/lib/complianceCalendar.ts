// Statutory filing deadlines are the same for every business of a given
// type/jurisdiction — unlike payments, payroll, or tasks, they don't need
// to be discovered from a tenant's documents. This is a small, static
// calendar of recurring obligations rather than something pulled from the
// knowledge base.
//
// Note: this defaults to the standard monthly GSTR-3B due date (20th).
// Businesses on the QRMP scheme or a different filing cadence would need
// a different rule — this is a general reminder, not a substitute for
// confirming the exact deadline with an accountant/GST portal.

export type ComplianceObligation = {
  id: string;
  label: string;
  description: string;
  dueDayOfMonth: number;
};

export const COMPLIANCE_CALENDAR: ComplianceObligation[] = [
  {
    id: 'gstr3b',
    label: 'GST filing',
    description: 'File GSTR-3B and pay any tax due',
    dueDayOfMonth: 20,
  },
];

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function getNextOccurrence(dueDayOfMonth: number, from: Date = new Date()): Date {
  const today = startOfDay(from);
  let due = new Date(today.getFullYear(), today.getMonth(), dueDayOfMonth);
  if (due < today) {
    due = new Date(today.getFullYear(), today.getMonth() + 1, dueDayOfMonth);
  }
  return due;
}

export function daysUntil(date: Date, from: Date = new Date()): number {
  const msPerDay = 24 * 60 * 60 * 1000;
  return Math.round((startOfDay(date).getTime() - startOfDay(from).getTime()) / msPerDay);
}

export function formatDueInDays(days: number): string {
  if (days === 0) return 'due today';
  if (days === 1) return 'due tomorrow';
  return `due in ${days} days`;
}

export function getNextComplianceDeadline(from: Date = new Date()) {
  const obligation = COMPLIANCE_CALENDAR[0];
  const dueDate = getNextOccurrence(obligation.dueDayOfMonth, from);
  const days = daysUntil(dueDate, from);
  return {
    obligation,
    dueDate,
    days,
    title: `${obligation.label} ${formatDueInDays(days)}`,
    formattedDate: dueDate.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }),
  };
}
