import {
  CheckCircle2,
  CircleCheck,
  PauseCircle,
  RotateCcw,
  XCircle,
} from 'lucide-react';

export const WORKFLOW_OPTIONS = [
  {
    value: 'approved',
    label: 'Approve',
    description: 'Ready to implement',
    icon: CheckCircle2,
    tone: 'approved',
    adminOnly: true,
    cta: 'Approve',
    quick: true,
  },
  {
    value: 'executed',
    label: 'Executed',
    description: 'Change applied',
    icon: CircleCheck,
    tone: 'executed',
    adminOnly: true,
    cta: 'Mark executed',
    quick: false,
  },
  {
    value: 'deferred',
    label: 'Defer',
    description: 'Review later',
    icon: PauseCircle,
    tone: 'deferred',
    cta: 'Defer',
    noteRequired: true,
    quick: true,
  },
  {
    value: 'rejected',
    label: 'Reject',
    description: 'Do not proceed',
    icon: XCircle,
    tone: 'rejected',
    adminOnly: true,
    cta: 'Reject',
    noteRequired: true,
    quick: true,
  },
  {
    value: 'proposed',
    label: 'Reopen',
    description: 'Back to proposed',
    icon: RotateCcw,
    tone: 'proposed',
    cta: 'Reopen',
    quick: false,
  },
];

export function workflowOptionForStatus(status) {
  return WORKFLOW_OPTIONS.find((option) => option.value === status) || null;
}

export function quickWorkflowOptions({ isAdmin, currentStatus = 'proposed' } = {}) {
  if (currentStatus !== 'proposed') return [];
  return WORKFLOW_OPTIONS.filter((option) => (
    option.quick
    && (!option.adminOnly || isAdmin)
  ));
}
