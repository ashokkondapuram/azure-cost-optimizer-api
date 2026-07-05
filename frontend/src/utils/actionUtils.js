/** Optimization action display helpers. */

export const ACTION_INDEX_LIMIT = 500;

const ACTION_LABELS = {
  resize_down: 'Resize down',
  keep: 'Keep',
  downgrade_disk: 'Downgrade disk',
  investigate: 'Investigate',
  buy_reservation: 'Buy reservation',
  manual_review: 'Manual review',
};

const WORKFLOW_LABELS = {
  proposed: 'Proposed',
  approved: 'Approved',
  executed: 'Executed',
  rejected: 'Rejected',
  deferred: 'Deferred',
};

const CONFIDENCE_TONES = {
  High: 'high',
  Medium: 'medium',
  Low: 'low',
  'Manual review': 'manual',
};

export function actionTypeLabel(actionType) {
  if (!actionType) return '—';
  return ACTION_LABELS[actionType] || String(actionType).replace(/_/g, ' ');
}

export function workflowStatusLabel(status) {
  if (!status) return 'Proposed';
  return WORKFLOW_LABELS[status] || status;
}

export function confidenceTone(confidence) {
  return CONFIDENCE_TONES[confidence] || 'muted';
}

export function actionMonthlySavings(action) {
  return action?.estimated_monthly_savings ?? null;
}

export function uniqueActionTypes(items = []) {
  return [...new Set(items.map((a) => a.action_type).filter(Boolean))].sort();
}

export function uniqueResourceTypes(items = []) {
  return [...new Set(items.map((a) => a.resource_type).filter(Boolean))].sort();
}
